import { useCallback, useRef, useState } from "react";

// In-browser microphone capture that yields a 16 kHz mono 16-bit WAV — the
// format VoClyp's ASR expects. MediaRecorder produces webm/opus which the ASR
// providers don't accept, so we capture raw PCM via Web Audio and encode the
// WAV ourselves. Ported from the existing VoClyp demo app.

const TARGET_RATE = 16000;

interface Live {
  stream: MediaStream;
  ctx: AudioContext;
  source: MediaStreamAudioSourceNode;
  proc: ScriptProcessorNode;
  chunks: Float32Array[];
  sampleRate: number;
}

function downsample(samples: Float32Array, fromRate: number, toRate: number): Float32Array {
  if (toRate >= fromRate) return samples;
  const ratio = fromRate / toRate;
  const out = new Float32Array(Math.floor(samples.length / ratio));
  for (let i = 0; i < out.length; i++) {
    const start = Math.floor(i * ratio);
    const end = Math.min(Math.floor((i + 1) * ratio), samples.length);
    let sum = 0;
    for (let j = start; j < end; j++) sum += samples[j];
    out[i] = sum / (end - start || 1);
  }
  return out;
}

function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const buf = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buf);
  const str = (o: number, s: string) => {
    for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i));
  };
  str(0, "RIFF");
  v.setUint32(4, 36 + samples.length * 2, true);
  str(8, "WAVE");
  str(12, "fmt ");
  v.setUint32(16, 16, true);
  v.setUint16(20, 1, true);
  v.setUint16(22, 1, true);
  v.setUint32(24, sampleRate, true);
  v.setUint32(28, sampleRate * 2, true);
  v.setUint16(32, 2, true);
  v.setUint16(34, 16, true);
  str(36, "data");
  v.setUint32(40, samples.length * 2, true);
  let off = 44;
  for (let i = 0; i < samples.length; i++, off += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    v.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buf], { type: "audio/wav" });
}

export function useRecorder() {
  const liveRef = useRef<Live | null>(null);
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [wav, setWav] = useState<Blob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<number | null>(null);

  const start = useCallback(async () => {
    setError(null);
    setWav(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const Ctx: typeof AudioContext =
        window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const ctx = new Ctx();
      const source = ctx.createMediaStreamSource(stream);
      const proc = ctx.createScriptProcessor(4096, 1, 1);
      const chunks: Float32Array[] = [];
      proc.onaudioprocess = (e) => chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
      source.connect(proc);
      proc.connect(ctx.destination);
      liveRef.current = { stream, ctx, source, proc, chunks, sampleRate: ctx.sampleRate };
      setRecording(true);
      setElapsed(0);
      const startedAt = Date.now();
      timerRef.current = window.setInterval(
        () => setElapsed(Math.floor((Date.now() - startedAt) / 1000)),
        250,
      );
    } catch (e) {
      setError(
        (e instanceof Error ? e.message : String(e)) +
          " — microphone needs localhost or https.",
      );
    }
  }, []);

  const stop = useCallback(() => {
    const live = liveRef.current;
    liveRef.current = null;
    if (timerRef.current) window.clearInterval(timerRef.current);
    setRecording(false);
    if (!live) return;
    live.proc.disconnect();
    live.source.disconnect();
    live.stream.getTracks().forEach((t) => t.stop());
    void live.ctx.close();

    let total = 0;
    for (const c of live.chunks) total += c.length;
    const all = new Float32Array(total);
    let off = 0;
    for (const c of live.chunks) {
      all.set(c, off);
      off += c.length;
    }
    setWav(encodeWav(downsample(all, live.sampleRate, TARGET_RATE), TARGET_RATE));
  }, []);

  const reset = useCallback(() => setWav(null), []);

  return { recording, elapsed, wav, error, start, stop, reset };
}

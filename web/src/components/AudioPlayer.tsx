import { useEffect, useRef, useState } from "react";
import { Icon } from "./Icon";
import { secondsToClock } from "../lib/format";
import "./audioplayer.css";

// Compact audio player: play/pause, scrubber, current/total time, volume,
// overflow menu. When there is no recording (VoClyp destroys the audio after
// processing), it renders that as a privacy guarantee instead of a dead player.
export function AudioPlayer({
  src,
  durationSec,
}: {
  src: string;
  durationSec: number;
}) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(durationSec || 0);
  const [volume, setVolume] = useState(1);

  useEffect(() => {
    const a = audioRef.current;
    if (!a) return;
    const onTime = () => setCurrent(a.currentTime);
    const onMeta = () => setDuration(a.duration || durationSec || 0);
    const onEnd = () => setPlaying(false);
    a.addEventListener("timeupdate", onTime);
    a.addEventListener("loadedmetadata", onMeta);
    a.addEventListener("ended", onEnd);
    return () => {
      a.removeEventListener("timeupdate", onTime);
      a.removeEventListener("loadedmetadata", onMeta);
      a.removeEventListener("ended", onEnd);
    };
  }, [durationSec]);

  if (!src) {
    return (
      <div className="audio audio--empty">
        <Icon name="volume" size={16} />
        <span>
          Recording not retained — audio is destroyed after processing
          (privacy guarantee).
        </span>
      </div>
    );
  }

  function toggle() {
    const a = audioRef.current;
    if (!a) return;
    if (playing) {
      a.pause();
      setPlaying(false);
    } else {
      void a.play();
      setPlaying(true);
    }
  }

  function seek(value: number) {
    const a = audioRef.current;
    if (!a) return;
    a.currentTime = value;
    setCurrent(value);
  }

  function changeVolume(value: number) {
    const a = audioRef.current;
    if (a) a.volume = value;
    setVolume(value);
  }

  const pct = duration ? (current / duration) * 100 : 0;

  return (
    <div className="audio">
      <audio ref={audioRef} src={src} preload="metadata" />
      <button className="audio__play" onClick={toggle} aria-label={playing ? "Pause" : "Play"}>
        <Icon name={playing ? "pause" : "play"} size={18} />
      </button>

      <div className="audio__scrub">
        <input
          type="range"
          min={0}
          max={duration || 0}
          step={0.1}
          value={current}
          onChange={(e) => seek(Number(e.target.value))}
          style={{ background: `linear-gradient(to right, var(--accent) ${pct}%, var(--border) ${pct}%)` }}
          aria-label="Seek"
        />
      </div>

      <span className="audio__time">
        {secondsToClock(current)} / {secondsToClock(duration)}
      </span>

      <div className="audio__vol">
        <Icon name="volume" size={16} />
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={volume}
          onChange={(e) => changeVolume(Number(e.target.value))}
          aria-label="Volume"
        />
      </div>

      <button className="audio__more" aria-label="More">
        <Icon name="more-vertical" size={16} />
      </button>
    </div>
  );
}

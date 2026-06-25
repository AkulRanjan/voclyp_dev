import { Audio } from 'expo-av';

/** iPhone: native AAC/m4a (reliable). Android: AAC m4a. Backend normalizes for Sarvam. */
export const FIELD_RECORDING_OPTIONS: Audio.RecordingOptions = {
  isMeteringEnabled: false,
  android: {
    extension: '.m4a',
    outputFormat: Audio.AndroidOutputFormat.MPEG_4,
    audioEncoder: Audio.AndroidAudioEncoder.AAC,
    sampleRate: 44100,
    numberOfChannels: 1,
    bitRate: 96000,
  },
  ios: {
    extension: '.m4a',
    outputFormat: Audio.IOSOutputFormat.MPEG4AAC,
    audioQuality: Audio.IOSAudioQuality.HIGH,
    sampleRate: 44100,
    numberOfChannels: 1,
    bitRate: 96000,
  },
  web: {
    mimeType: 'audio/webm',
    bitsPerSecond: 128000,
  },
};

export function audioUploadName(uri: string | null | undefined): string {
  if (!uri) return 'visit.m4a';
  const lower = uri.toLowerCase();
  if (lower.endsWith('.m4a')) return 'visit.m4a';
  if (lower.endsWith('.wav')) return 'visit.wav';
  if (lower.endsWith('.aac')) return 'visit.aac';
  return 'visit.m4a';
}

export function audioUploadMime(uri: string | null | undefined): string {
  const name = audioUploadName(uri);
  if (name.endsWith('.m4a')) return 'audio/m4a';
  if (name.endsWith('.aac')) return 'audio/aac';
  return 'audio/wav';
}

export interface ArollCut {
  srcStartSec: number;
  srcEndSec: number;
  outStartFrame: number;
  durationFrames: number;
  zoom: number;
}

export interface BrollOverlay {
  src: string;
  outStartFrame: number;
  durationFrames: number;
  filter: 'crt-chromatic';
  transition: 'glitch' | 'light-leak';
}

export interface CaptionWord {
  text: string;
  startFrame: number;
  endFrame: number;
  isNeon: boolean;
}

export interface CaptionBlock {
  startFrame: number;
  endFrame: number;
  words: CaptionWord[];
}

export interface SfxEvent {
  type: 'whoosh' | 'pop' | 'impact';
  frame: number;
  volume: number;
}

export interface TimelineData {
  fps: number;
  width: number;
  height: number;
  durationInFrames: number;
  arollSrc: string;
  arollCuts: ArollCut[];
  brollOverlays: BrollOverlay[];
  captions: CaptionBlock[];
  sfxEvents: SfxEvent[];
}

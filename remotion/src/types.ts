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
  clipStartSec?: number;
  filter: 'crt-chromatic';
  transition: 'glitch' | 'light-leak';
}

export interface CaptionWord {
  text: string;
  startFrame: number;
  endFrame: number;
  isNeon: boolean;
  neonColor?: 'green' | 'red';
}

export interface CaptionBlock {
  startFrame: number;
  endFrame: number;
  words: CaptionWord[];
}

export interface CalloutOverlay {
  type: 'url_card' | 'follow_badge' | 'store_badge' | 'step_card';
  outStartFrame: number;
  durationFrames: number;
  primaryText: string;
  secondaryText?: string;
}

export interface SfxEvent {
  type: 'whoosh' | 'pop' | 'impact';
  frame: number;
  volume: number;
}

export interface BgmConfig {
  enabled: boolean;
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
  callouts?: CalloutOverlay[];
  sfxEvents: SfxEvent[];
  bgm?: BgmConfig;
}

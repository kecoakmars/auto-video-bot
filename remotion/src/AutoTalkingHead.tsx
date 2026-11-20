import React from 'react';
import {
  AbsoluteFill,
  Audio,
  OffthreadVideo,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import { ArollCut, TimelineData } from './types';
import { CrtBrollLayer } from './effects/CrtBrollLayer';
import { NeonCaptions } from './effects/NeonCaptions';

const ArollClip: React.FC<{ src: string; cut: ArollCut }> = ({ src, cut }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const punch = spring({
    frame,
    fps,
    config: { damping: 18, stiffness: 180, mass: 0.7 },
  });

  const targetZoom = cut.zoom > 1 ? cut.zoom : 1.0;
  const startZoom = cut.zoom > 1 ? 1.03 : 1.0;
  const baseScale = interpolate(punch, [0, 1], [startZoom, targetZoom]);
  const microDrift = interpolate(frame, [0, cut.durationFrames], [0, 0.025], {
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill style={{ overflow: 'hidden', backgroundColor: '#000' }}>
      <OffthreadVideo
        src={staticFile(src)}
        startFrom={Math.round(cut.srcStartSec * fps)}
        endAt={Math.round(cut.srcEndSec * fps)}
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          transform: `scale(${baseScale + microDrift})`,
        }}
      />
    </AbsoluteFill>
  );
};

export const AutoTalkingHead: React.FC<{ timeline: TimelineData }> = ({ timeline }) => {
  return (
    <AbsoluteFill style={{ backgroundColor: '#000000' }}>
      {/* Lapisan 1: Potongan A-Roll + Punch-In Zoom */}
      {timeline.arollCuts.map((cut, idx) => (
        <Sequence
          key={`aroll-${idx}`}
          from={cut.outStartFrame}
          durationInFrames={cut.durationFrames}
        >
          <ArollClip src={timeline.arollSrc} cut={cut} />
        </Sequence>
      ))}

      {/* Lapisan 2: B-Roll Efek CRT & Chromatic Aberration */}
      {timeline.brollOverlays.map((broll, idx) => (
        <Sequence
          key={`broll-${idx}`}
          from={broll.outStartFrame}
          durationInFrames={broll.durationFrames}
        >
          <CrtBrollLayer overlay={broll} />
        </Sequence>
      ))}

      {/* Lapisan 3: Subtitle Putih & Hijau Neon */}
      <NeonCaptions captions={timeline.captions} />

      {/* Lapisan 4: Efek Suara Otomatis */}
      {timeline.sfxEvents.map((sfx, idx) => (
        <Sequence key={`sfx-${idx}`} from={sfx.frame} durationInFrames={30}>
          <Audio src={staticFile(`sfx/${sfx.type}.wav`)} volume={sfx.volume} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};

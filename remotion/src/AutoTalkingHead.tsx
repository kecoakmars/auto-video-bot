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
import './fonts';
import { ArollCut, TimelineData } from './types';
import { CrtBrollLayer } from './effects/CrtBrollLayer';
import { NeonCaptions } from './effects/NeonCaptions';
import { CalloutOverlayLayer } from './effects/CalloutOverlayLayer';

const ArollClip: React.FC<{ src: string; cut: ArollCut; isFirst: boolean }> = ({
  src,
  cut,
  isFirst,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const punch = spring({
    frame,
    fps,
    config: { damping: 16, stiffness: 200, mass: 0.65 },
  });

  const targetZoom = cut.zoom > 1 ? cut.zoom : 1.0;
  const startZoom = cut.zoom > 1 ? 1.02 : 1.0;
  const baseScale = interpolate(punch, [0, 1], [startZoom, targetZoom]);

  // Dorongan zoom halus agar frame hidup tanpa menggeser posisi wajah
  const microPush = interpolate(frame, [0, Math.max(1, cut.durationFrames)], [0, 0.015], {
    extrapolateRight: 'clamp',
  });

  // Efek blur-in & fade-in halus pada klip pembuka pertama
  const introBlur = isFirst
    ? interpolate(frame, [0, 8], [10, 0], { extrapolateRight: 'clamp' })
    : 0;
  const introOpacity = isFirst
    ? interpolate(frame, [0, 6], [0.2, 1], { extrapolateRight: 'clamp' })
    : 1;

  return (
    <AbsoluteFill
      style={{
        overflow: 'hidden',
        backgroundColor: '#000',
        opacity: introOpacity,
        filter: introBlur > 0 ? `blur(${introBlur}px)` : undefined,
      }}
    >
      <OffthreadVideo
        src={staticFile(src)}
        startFrom={Math.max(0, Math.round(cut.srcStartSec * fps))}
        endAt={Math.max(1, Math.round(cut.srcEndSec * fps))}
        volume={(f) =>
          interpolate(
            f,
            [0, 2, Math.max(3, cut.durationFrames - 3), Math.max(4, cut.durationFrames)],
            [0, 1, 1, 0],
            { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
          )
        }
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          objectPosition: 'center center',
          transformOrigin: '50% 34%',
          transform: `scale(${baseScale + microPush})`,
        }}
      />
    </AbsoluteFill>
  );
};

export const AutoTalkingHead: React.FC<{ timeline: TimelineData }> = ({ timeline }) => {
  const bgmEnabled = Boolean(timeline.bgm?.enabled);
  const bgmVolume = timeline.bgm?.volume ?? 0.09;

  return (
    <AbsoluteFill style={{ backgroundColor: '#000000' }}>
      {/* Lapisan 1: Potongan A-Roll Bersih + Punch-In Zoom Terpusat */}
      {timeline.arollCuts.map((cut, idx) => (
        <Sequence
          key={`aroll-${idx}`}
          from={cut.outStartFrame}
          durationInFrames={Math.max(1, cut.durationFrames)}
        >
          <ArollClip src={timeline.arollSrc} cut={cut} isFirst={idx === 0} />
        </Sequence>
      ))}

      {/* Lapisan 2: B-Roll Tutorial Layar Penuh dengan Efek CRT & Transisi */}
      {timeline.brollOverlays.map((broll, idx) => (
        <Sequence
          key={`broll-${idx}`}
          from={broll.outStartFrame}
          durationInFrames={Math.max(1, broll.durationFrames)}
        >
          <CrtBrollLayer overlay={broll} />
        </Sequence>
      ))}

      {/* Lapisan 3: Kartu Callout Otomatis (URL, Follow Badge, Store Badge) */}
      <CalloutOverlayLayer callouts={timeline.callouts ?? []} />

      {/* Lapisan 4: Subtitle Tebal ALL-CAPS Putih & Neon */}
      <NeonCaptions captions={timeline.captions} />

      {/* Lapisan 5: Efek Suara Transisi & Pop */}
      {timeline.sfxEvents.map((sfx, idx) => (
        <Sequence key={`sfx-${idx}`} from={sfx.frame} durationInFrames={30}>
          <Audio src={staticFile(`sfx/${sfx.type}.wav`)} volume={sfx.volume} />
        </Sequence>
      ))}

      {/* Lapisan 6: Musik Latar (BGM) Loop Lembut */}
      {bgmEnabled ? (
        <Audio src={staticFile('sfx/bgm.wav')} loop volume={bgmVolume} />
      ) : null}
    </AbsoluteFill>
  );
};

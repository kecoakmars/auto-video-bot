import React from 'react';
import {
  AbsoluteFill,
  OffthreadVideo,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import { BrollOverlay } from '../types';

export const CrtBrollLayer: React.FC<{ overlay: BrollOverlay }> = ({ overlay }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const startFrame = Math.max(0, Math.round((overlay.clipStartSec ?? 0) * fps));

  // Zoom perlahan agar B-roll terasa hidup tanpa memotong teks di pinggir layar
  const slowScale = interpolate(frame, [0, overlay.durationFrames], [1.01, 1.07], {
    extrapolateRight: 'clamp',
  });

  // Efek transisi masuk 7 frame pertama
  const isGlitch = overlay.transition === 'glitch';
  const glitchOffset =
    isGlitch && frame < 7 ? (frame % 2 === 0 ? 16 : -16) * (1 - frame / 7) : 0;

  const leakOpacity =
    !isGlitch && frame < 10
      ? interpolate(frame, [0, 3, 10], [0.85, 0.55, 0], { extrapolateRight: 'clamp' })
      : 0;

  return (
    <AbsoluteFill style={{ backgroundColor: '#050805', overflow: 'hidden' }}>
      {/* Lapisan Chromatic Aberration halus di tepi */}
      <AbsoluteFill
        style={{
          transform: `scale(${slowScale}) translateX(${-3 + glitchOffset}px)`,
          opacity: 0.45,
          mixBlendMode: 'screen',
          filter: 'contrast(1.2) saturate(1.25)',
        }}
      >
        <OffthreadVideo
          src={staticFile(overlay.src)}
          startFrom={startFrame}
          muted
          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
        />
      </AbsoluteFill>

      {/* Lapisan Utama B-Roll (tajam & jelas untuk tutorial layar) */}
      <AbsoluteFill
        style={{
          transform: `scale(${slowScale}) translateX(${2 - glitchOffset}px)`,
          opacity: 0.96,
          filter: 'contrast(1.12) saturate(1.08)',
        }}
      >
        <OffthreadVideo
          src={staticFile(overlay.src)}
          startFrom={startFrame}
          muted
          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
        />
      </AbsoluteFill>

      {/* Kisi Garis Layar CRT tipis agar teks layar tetap terbaca */}
      <AbsoluteFill
        style={{
          backgroundImage:
            'repeating-linear-gradient(0deg, rgba(0, 0, 0, 0.22) 0px, rgba(0, 0, 0, 0.22) 2px, transparent 2px, transparent 6px)',
          pointerEvents: 'none',
        }}
      />

      {/* Vignette Gelap di Pinggir Layar */}
      <AbsoluteFill
        style={{
          background:
            'radial-gradient(circle, rgba(0,0,0,0) 58%, rgba(0,0,0,0.62) 100%)',
          pointerEvents: 'none',
        }}
      />

      {/* Kilatan Light Leak Hijau Neon saat Transisi */}
      {leakOpacity > 0 && (
        <AbsoluteFill
          style={{
            background:
              'radial-gradient(circle at 30% 25%, rgba(57, 255, 20, 0.85), rgba(255, 255, 255, 0.4) 35%, transparent 70%)',
            opacity: leakOpacity,
            mixBlendMode: 'screen',
            pointerEvents: 'none',
          }}
        />
      )}
    </AbsoluteFill>
  );
};

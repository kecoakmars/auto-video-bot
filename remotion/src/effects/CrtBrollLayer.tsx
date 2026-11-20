import React from 'react';
import {
  AbsoluteFill,
  OffthreadVideo,
  interpolate,
  staticFile,
  useCurrentFrame,
} from 'remotion';
import { BrollOverlay } from '../types';

export const CrtBrollLayer: React.FC<{ overlay: BrollOverlay }> = ({ overlay }) => {
  const frame = useCurrentFrame();

  // Zoom perlahan agar B-roll terasa hidup
  const slowScale = interpolate(frame, [0, overlay.durationFrames], [1.03, 1.11], {
    extrapolateRight: 'clamp',
  });

  // Efek transisi masuk 7 frame pertama
  const isGlitch = overlay.transition === 'glitch';
  const glitchOffset =
    isGlitch && frame < 7 ? (frame % 2 === 0 ? 14 : -14) * (1 - frame / 7) : 0;

  const leakOpacity =
    !isGlitch && frame < 10
      ? interpolate(frame, [0, 3, 10], [0.85, 0.6, 0], { extrapolateRight: 'clamp' })
      : 0;

  return (
    <AbsoluteFill style={{ backgroundColor: '#050805', overflow: 'hidden' }}>
      {/* Lapisan Chromatic Aberration (Kanal Merah/Hijau) */}
      <AbsoluteFill
        style={{
          transform: `scale(${slowScale}) translateX(${-4 + glitchOffset}px)`,
          opacity: 0.55,
          mixBlendMode: 'screen',
          filter: 'contrast(1.25) saturate(1.3)',
        }}
      >
        <OffthreadVideo
          src={staticFile(overlay.src)}
          muted
          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
        />
      </AbsoluteFill>

      {/* Lapisan Utama B-Roll */}
      <AbsoluteFill
        style={{
          transform: `scale(${slowScale}) translateX(${3 - glitchOffset}px)`,
          opacity: 0.88,
          filter: 'contrast(1.18) brightness(0.92)',
        }}
      >
        <OffthreadVideo
          src={staticFile(overlay.src)}
          muted
          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
        />
      </AbsoluteFill>

      {/* Kisi Garis Layar CRT (Scanlines) */}
      <AbsoluteFill
        style={{
          backgroundImage:
            'repeating-linear-gradient(0deg, rgba(0, 0, 0, 0.36) 0px, rgba(0, 0, 0, 0.36) 2px, transparent 2px, transparent 5px)',
          pointerEvents: 'none',
        }}
      />

      {/* Vignette Gelap di Pinggir Layar */}
      <AbsoluteFill
        style={{
          background:
            'radial-gradient(circle, rgba(0,0,0,0) 52%, rgba(0,0,0,0.68) 100%)',
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

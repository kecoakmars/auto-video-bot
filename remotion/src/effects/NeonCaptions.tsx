import React from 'react';
import { AbsoluteFill, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import '../fonts';
import { CaptionBlock } from '../types';

export const NeonCaptions: React.FC<{ captions: CaptionBlock[] }> = ({ captions }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const activeBlock = captions.find(
    (c) => frame >= c.startFrame && frame <= c.endFrame
  );

  if (!activeBlock) {
    return null;
  }

  return (
    <AbsoluteFill
      style={{
        justifyContent: 'flex-end',
        alignItems: 'center',
        paddingBottom: 440, // Zona aman di atas UI bawah TikTok/Reels
        paddingLeft: 70,
        paddingRight: 110, // Zona aman dari tombol kanan
        pointerEvents: 'none',
      }}
    >
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'center',
          alignItems: 'center',
          gap: '12px 18px',
          textAlign: 'center',
        }}
      >
        {activeBlock.words.map((w, idx) => {
          const isSpoken = frame >= w.startFrame;
          const pop = spring({
            frame: Math.max(0, frame - w.startFrame),
            fps,
            config: { damping: 13, stiffness: 280, mass: 0.45 },
          });

          const isRed = w.neonColor === 'red';
          const neonHex = isRed ? '#FF3B30' : '#39FF14';
          const neonGlow = isRed
            ? '0 0 16px rgba(255, 59, 48, 0.95), 0 0 36px rgba(255, 59, 48, 0.6), 0 6px 14px rgba(0, 0, 0, 0.98)'
            : '0 0 16px rgba(57, 255, 20, 0.95), 0 0 36px rgba(57, 255, 20, 0.6), 0 6px 14px rgba(0, 0, 0, 0.98)';

          const baseScale = w.isNeon ? 1.14 : 1.0;
          const activeScale = isSpoken ? baseScale * (0.88 + 0.12 * pop) : 0.92;

          return (
            <span
              key={idx}
              style={{
                fontFamily: 'Geist, Montserrat, Inter, system-ui, sans-serif',
                fontWeight: 900,
                fontSize: w.isNeon ? 76 : 68,
                lineHeight: 1.12,
                textTransform: 'uppercase',
                letterSpacing: '-0.02em',
                color: w.isNeon ? neonHex : '#FFFFFF',
                opacity: isSpoken ? 1 : 0.45,
                transform: `scale(${activeScale})`,
                display: 'inline-block',
                paintOrder: 'stroke fill',
                WebkitTextStroke: '7px #000000',
                textShadow: w.isNeon
                  ? neonGlow
                  : '0 6px 14px rgba(0, 0, 0, 0.98), 0 2px 4px rgba(0, 0, 0, 1)',
              }}
            >
              {w.text}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

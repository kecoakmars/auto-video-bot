import React from 'react';
import { AbsoluteFill, spring, useCurrentFrame, useVideoConfig } from 'remotion';
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
        paddingBottom: 430, // Zona aman di atas UI bawah TikTok/Reels
        paddingLeft: 80,
        paddingRight: 110, // Zona aman dari tombol Like/Comment kanan
        pointerEvents: 'none',
      }}
    >
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'center',
          alignItems: 'center',
          gap: '14px 18px',
          textAlign: 'center',
        }}
      >
        {activeBlock.words.map((w, idx) => {
          const isSpoken = frame >= w.startFrame;
          const pop = spring({
            frame: Math.max(0, frame - w.startFrame),
            fps,
            config: { damping: 14, stiffness: 260, mass: 0.5 },
          });

          const baseScale = w.isNeon ? 1.12 : 1.0;
          const activeScale = isSpoken ? baseScale * (0.9 + 0.1 * pop) : 0.94;

          return (
            <span
              key={idx}
              style={{
                fontFamily: 'Inter, Montserrat, system-ui, -apple-system, sans-serif',
                fontWeight: 900,
                fontSize: w.isNeon ? 68 : 60,
                lineHeight: 1.15,
                textTransform: 'uppercase',
                letterSpacing: '-0.02em',
                color: w.isNeon ? '#39FF14' : '#FFFFFF',
                opacity: isSpoken ? 1 : 0.42,
                transform: `scale(${activeScale})`,
                display: 'inline-block',
                textShadow: w.isNeon
                  ? '0 0 14px rgba(57, 255, 20, 0.9), 0 0 32px rgba(57, 255, 20, 0.55), 0 5px 12px rgba(0, 0, 0, 0.95)'
                  : '0 4px 12px rgba(0, 0, 0, 0.95), 0 0 4px rgba(0, 0, 0, 0.9)',
                WebkitTextStroke: '2px rgba(0, 0, 0, 0.85)',
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

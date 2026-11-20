import React from 'react';
import {
  AbsoluteFill,
  Sequence,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import '../fonts';
import { CalloutOverlay } from '../types';

const CalloutCardItem: React.FC<{ item: CalloutOverlay }> = ({ item }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const enter = spring({
    frame,
    fps,
    config: { damping: 13, stiffness: 210, mass: 0.65 },
  });

  const exit = interpolate(
    frame,
    [Math.max(0, item.durationFrames - 8), item.durationFrames],
    [1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
  );

  const opacity = Math.min(enter, exit);
  const scale = interpolate(enter, [0, 1], [0.82, 1]) * (0.94 + 0.06 * exit);
  const translateY = interpolate(enter, [0, 1], [28, 0]);

  if (item.type === 'follow_badge') {
    return (
      <div
        style={{
          opacity,
          transform: `translateY(${translateY}px) scale(${scale})`,
          display: 'flex',
          alignItems: 'center',
          gap: 18,
          background: 'rgba(14, 14, 18, 0.94)',
          border: '2px solid rgba(255, 59, 48, 0.75)',
          borderRadius: 999,
          padding: '16px 34px 16px 20px',
          boxShadow:
            '0 20px 50px rgba(0, 0, 0, 0.65), 0 0 28px rgba(255, 59, 48, 0.35)',
        }}
      >
        <div
          style={{
            width: 58,
            height: 58,
            borderRadius: 999,
            background: 'linear-gradient(135deg, #FF3B30, #FF2D55)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#FFFFFF',
            fontSize: 32,
            fontWeight: 900,
            boxShadow: '0 0 18px rgba(255, 59, 48, 0.8)',
          }}
        >
          ✓
        </div>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <span
            style={{
              fontFamily: 'Geist, system-ui, sans-serif',
              fontSize: 34,
              fontWeight: 900,
              color: '#FFFFFF',
              letterSpacing: '-0.02em',
              textTransform: 'uppercase',
            }}
          >
            {item.primaryText || 'FOLLOW DULU'}
          </span>
          {item.secondaryText ? (
            <span
              style={{
                fontFamily: 'Geist, system-ui, sans-serif',
                fontSize: 22,
                fontWeight: 600,
                color: 'rgba(255, 255, 255, 0.72)',
              }}
            >
              {item.secondaryText}
            </span>
          ) : null}
        </div>
      </div>
    );
  }

  if (item.type === 'store_badge') {
    return (
      <div
        style={{
          opacity,
          transform: `translateY(${translateY}px) scale(${scale})`,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 14,
          background: 'rgba(14, 14, 18, 0.94)',
          border: '2px solid rgba(57, 255, 20, 0.55)',
          borderRadius: 28,
          padding: '22px 34px',
          boxShadow:
            '0 24px 60px rgba(0, 0, 0, 0.7), 0 0 30px rgba(57, 255, 20, 0.25)',
        }}
      >
        <div style={{ display: 'flex', gap: 16 }}>
          <div
            style={{
              background: '#FFFFFF',
              color: '#0D0D10',
              borderRadius: 16,
              padding: '12px 24px',
              fontFamily: 'Geist, system-ui, sans-serif',
              fontSize: 28,
              fontWeight: 800,
              display: 'flex',
              alignItems: 'center',
              gap: 10,
            }}
          >
            <span>▶</span> Google Play
          </div>
          <div
            style={{
              background: '#FFFFFF',
              color: '#0D0D10',
              borderRadius: 16,
              padding: '12px 24px',
              fontFamily: 'Geist, system-ui, sans-serif',
              fontSize: 28,
              fontWeight: 800,
              display: 'flex',
              alignItems: 'center',
              gap: 10,
            }}
          >
            <span></span> App Store
          </div>
        </div>
        {item.primaryText ? (
          <div
            style={{
              fontFamily: 'Geist, system-ui, sans-serif',
              fontSize: 26,
              fontWeight: 700,
              color: '#39FF14',
              letterSpacing: '0.03em',
              textTransform: 'uppercase',
            }}
          >
            {item.primaryText}
          </div>
        ) : null}
      </div>
    );
  }

  const isUrl = item.type === 'url_card';

  return (
    <div
      style={{
        opacity,
        transform: `translateY(${translateY}px) scale(${scale})`,
        maxWidth: 880,
        background: 'rgba(12, 14, 16, 0.95)',
        border: '2px solid rgba(57, 255, 20, 0.7)',
        borderRadius: 26,
        padding: '24px 38px',
        boxShadow:
          '0 26px 65px rgba(0, 0, 0, 0.78), 0 0 34px rgba(57, 255, 20, 0.28)',
        textAlign: 'center',
      }}
    >
      {item.secondaryText ? (
        <div
          style={{
            fontFamily: 'Geist, system-ui, sans-serif',
            fontSize: 24,
            fontWeight: 700,
            color: 'rgba(255, 255, 255, 0.72)',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            marginBottom: 8,
          }}
        >
          {item.secondaryText}
        </div>
      ) : null}
      <div
        style={{
          fontFamily: isUrl
            ? "'Geist Mono', monospace"
            : 'Geist, system-ui, sans-serif',
          fontSize: isUrl ? 48 : 44,
          fontWeight: 900,
          color: '#39FF14',
          letterSpacing: isUrl ? '-0.02em' : '-0.01em',
          textShadow: '0 0 18px rgba(57, 255, 20, 0.5)',
          wordBreak: 'break-word',
        }}
      >
        {item.primaryText}
      </div>
    </div>
  );
};

export const CalloutOverlayLayer: React.FC<{ callouts?: CalloutOverlay[] }> = ({
  callouts = [],
}) => {
  if (!callouts || callouts.length === 0) {
    return null;
  }

  return (
    <>
      {callouts.map((item, idx) => (
        <Sequence
          key={`callout-${idx}`}
          from={item.outStartFrame}
          durationInFrames={item.durationFrames}
        >
          <AbsoluteFill
            style={{
              justifyContent: 'flex-start',
              alignItems: 'center',
              paddingTop: 250, // Zona aman atas (tidak menutupi wajah & subtitle)
              paddingLeft: 60,
              paddingRight: 90,
              pointerEvents: 'none',
            }}
          >
            <CalloutCardItem item={item} />
          </AbsoluteFill>
        </Sequence>
      ))}
    </>
  );
};

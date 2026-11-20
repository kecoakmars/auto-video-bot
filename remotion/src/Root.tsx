import React from 'react';
import { CalculateMetadataFunction, Composition, staticFile } from 'remotion';
import { AutoTalkingHead } from './AutoTalkingHead';
import { TimelineData } from './types';

type Props = {
  timeline: TimelineData;
};

const defaultTimeline: TimelineData = {
  fps: 30,
  width: 1080,
  height: 1920,
  durationInFrames: 90,
  arollSrc: 'aroll.mp4',
  arollCuts: [],
  brollOverlays: [],
  captions: [],
  sfxEvents: [],
};

const calculateMetadata: CalculateMetadataFunction<Props> = async () => {
  const response = await fetch(staticFile('timeline.json'));
  const data: TimelineData = await response.json();
  return {
    durationInFrames: data.durationInFrames,
    fps: data.fps || 30,
    width: data.width || 1080,
    height: data.height || 1920,
    props: { timeline: data },
  };
};

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="AutoTalkingHead"
      component={AutoTalkingHead}
      durationInFrames={90}
      fps={30}
      width={1080}
      height={1920}
      defaultProps={{ timeline: defaultTimeline }}
      calculateMetadata={calculateMetadata}
    />
  );
};

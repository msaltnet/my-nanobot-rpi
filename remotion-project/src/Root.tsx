import {Composition} from 'remotion';
import {NanobotIntro} from './NanobotIntro';

export const RemotionRoot = () => {
  return (
    <Composition
      id="NanobotIntro"
      component={NanobotIntro}
      durationInFrames={900}
      fps={30}
      width={1920}
      height={1080}
    />
  );
};

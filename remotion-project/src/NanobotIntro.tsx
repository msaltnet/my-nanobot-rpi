import React from 'react';
import {
  AbsoluteFill,
  Easing,
  interpolate,
  Sequence,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

const palette = {
  night: '#101820',
  desk: '#d9d0c3',
  paper: '#f7f4ed',
  ink: '#17212b',
  muted: '#6d7780',
  green: '#4ec7a3',
  blue: '#3f8cff',
  yellow: '#ffc857',
  coral: '#ff6b5f',
  violet: '#7b61ff',
  line: 'rgba(23, 33, 43, 0.16)',
};

const ease = Easing.bezier(0.16, 1, 0.3, 1);
const second = (value: number, fps: number) => Math.round(value * fps);

const clamp = {
  extrapolateLeft: 'clamp' as const,
  extrapolateRight: 'clamp' as const,
};

const sceneFade = (frame: number, fps: number, seconds: number) => {
  const inOpacity = interpolate(frame, [0, second(0.45, fps)], [0, 1], {...clamp, easing: ease});
  const outOpacity = interpolate(
    frame,
    [second(seconds - 0.55, fps), second(seconds, fps)],
    [1, 0],
    {...clamp, easing: ease},
  );
  return inOpacity * outOpacity;
};

const rise = (frame: number, fps: number, delay = 0, distance = 28) =>
  interpolate(frame, [second(delay, fps), second(delay + 0.7, fps)], [distance, 0], {
    ...clamp,
    easing: ease,
  });

const Caption = ({children}: {children: React.ReactNode}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  return (
    <div
      style={{
        position: 'absolute',
        left: 120,
        bottom: 70,
        width: 840,
        transform: `translateY(${rise(frame, fps, 0.1, 18)}px)`,
        borderRadius: 8,
        background: 'rgba(16, 24, 32, 0.74)',
        padding: '22px 30px 24px',
        fontSize: 44,
        lineHeight: 1.2,
        fontWeight: 900,
        letterSpacing: 0,
        color: palette.paper,
        textShadow: '0 2px 14px rgba(0,0,0,0.2)',
      }}
    >
      {children}
    </div>
  );
};

const Stage = ({children}: {children: React.ReactNode}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const light = interpolate(frame, [0, second(30, fps)], [0, 1], clamp);

  return (
    <AbsoluteFill style={{background: palette.night, overflow: 'hidden'}}>
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background:
            'linear-gradient(180deg, #101820 0%, #17212b 42%, #2f2a26 42%, #d9d0c3 43%, #c7b9a7 100%)',
        }}
      />
      <div
        style={{
          position: 'absolute',
          left: -120,
          top: 0,
          width: 980,
          height: 1080,
          background: `rgba(255, 226, 166, ${0.06 + light * 0.07})`,
          clipPath: 'polygon(0 0, 58% 0, 100% 100%, 0 100%)',
        }}
      />
      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          top: 454,
          height: 4,
          background: 'rgba(255,255,255,0.12)',
        }}
      />
      <div style={{position: 'absolute', left: 108, top: 70, color: palette.paper, fontSize: 24, fontWeight: 800}}>
        my-nanobot-rpi
      </div>
      {children}
    </AbsoluteFill>
  );
};

const AlertCard = ({
  top,
  delay,
  color,
  title,
  detail,
}: {
  top: number;
  delay: number;
  color: string;
  title: string;
  detail: string;
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const opacity = interpolate(frame, [second(delay, fps), second(delay + 0.45, fps)], [0, 1], {
    ...clamp,
    easing: ease,
  });
  const y = rise(frame, fps, delay, 42);

  return (
    <div
      style={{
        position: 'absolute',
        left: 1060,
        top,
        width: 540,
        height: 96,
        borderRadius: 18,
        background: 'rgba(247,244,237,0.94)',
        border: `2px solid ${palette.ink}`,
        boxShadow: '0 16px 40px rgba(0,0,0,0.22)',
        opacity,
        transform: `translateY(${y}px)`,
        display: 'flex',
        alignItems: 'center',
        gap: 20,
        padding: '0 24px',
      }}
    >
      <div style={{width: 18, height: 58, borderRadius: 999, background: color}} />
      <div>
        <div style={{fontSize: 27, fontWeight: 900, color: palette.ink}}>{title}</div>
        <div style={{marginTop: 7, fontSize: 20, fontWeight: 700, color: palette.muted}}>{detail}</div>
      </div>
    </div>
  );
};

const Phone = ({children, compact = false}: {children: React.ReactNode; compact?: boolean}) => (
  <div
    style={{
      width: compact ? 470 : 560,
      height: compact ? 720 : 820,
      borderRadius: 54,
      background: '#07111a',
      border: '5px solid #0b0f13',
      boxShadow: '28px 34px 70px rgba(0,0,0,0.36)',
      padding: 18,
    }}
  >
    <div
      style={{
        width: '100%',
        height: '100%',
        borderRadius: 38,
        overflow: 'hidden',
        background: '#edf5fa',
        position: 'relative',
      }}
    >
      <div
        style={{
          height: 82,
          background: '#1e9bd7',
          color: 'white',
          display: 'flex',
          alignItems: 'center',
          padding: '0 30px',
          gap: 16,
        }}
      >
        <div style={{width: 42, height: 42, borderRadius: 999, background: '#0f6fa3'}} />
        <div>
          <div style={{fontSize: 25, fontWeight: 900}}>my-nanobot-rpi</div>
          <div style={{fontSize: 17, fontWeight: 700, opacity: 0.86}}>online</div>
        </div>
      </div>
      <div style={{position: 'absolute', inset: '82px 0 0 0', padding: 24}}>{children}</div>
    </div>
  </div>
);

const Bubble = ({
  children,
  from = 'bot',
  delay = 0,
}: {
  children: React.ReactNode;
  from?: 'bot' | 'me';
  delay?: number;
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const opacity = interpolate(frame, [second(delay, fps), second(delay + 0.35, fps)], [0, 1], {
    ...clamp,
    easing: ease,
  });

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: from === 'me' ? 'flex-end' : 'flex-start',
        opacity,
        transform: `translateY(${rise(frame, fps, delay, 18)}px)`,
        marginBottom: 16,
      }}
    >
      <div
        style={{
          maxWidth: '86%',
          background: from === 'me' ? '#d8f7c5' : '#ffffff',
          borderRadius: from === 'me' ? '22px 22px 4px 22px' : '22px 22px 22px 4px',
          padding: '18px 20px',
          fontSize: 23,
          lineHeight: 1.33,
          fontWeight: 760,
          color: palette.ink,
          boxShadow: '0 6px 18px rgba(23,33,43,0.1)',
          whiteSpace: 'pre-line',
        }}
      >
        {children}
      </div>
    </div>
  );
};

const PiServer = () => {
  const frame = useCurrentFrame();
  const blink = interpolate(Math.sin(frame / 8), [-1, 1], [0.35, 1]);

  return (
    <div style={{position: 'relative', width: 520, height: 340}}>
      <div
        style={{
          position: 'absolute',
          left: 24,
          right: 24,
          bottom: 0,
          height: 70,
          borderRadius: '50%',
          background: 'rgba(0,0,0,0.2)',
          filter: 'blur(12px)',
        }}
      />
      <div
        style={{
          position: 'absolute',
          left: 44,
          top: 50,
          width: 430,
          height: 230,
          borderRadius: 20,
          background: '#25715f',
          border: '4px solid #0c2b25',
          boxShadow: '18px 20px 0 rgba(0,0,0,0.18)',
        }}
      >
        {Array.from({length: 12}).map((_, index) => (
          <div
            key={index}
            style={{
              position: 'absolute',
              left: 30 + index * 31,
              top: 22,
              width: 15,
              height: 30,
              background: palette.yellow,
              border: '2px solid #0c2b25',
            }}
          />
        ))}
        <div style={{position: 'absolute', left: 92, top: 82, width: 180, height: 96, borderRadius: 12, background: '#121c22', border: '3px solid #0c2b25'}}>
          <div style={{position: 'absolute', left: 28, top: 24, color: palette.paper, fontSize: 24, fontWeight: 900}}>agent</div>
          <div style={{position: 'absolute', left: 28, top: 58, color: 'rgba(247,244,237,0.65)', fontSize: 17, fontWeight: 800}}>local brain</div>
        </div>
        <div style={{position: 'absolute', right: 42, bottom: 38, width: 64, height: 64, borderRadius: 999, background: `rgba(78,199,163,${blink})`, border: '3px solid #0c2b25'}} />
      </div>
    </div>
  );
};

const Terminal = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const rows = [
    ['$ my-nanobot-rpi doctor', palette.paper],
    ['RSS sources       ok', palette.green],
    ['Telegram gateway  ok', palette.green],
    ['SQLite storage    ok', palette.green],
    ['systemd service   active', palette.blue],
  ];

  return (
    <div
      style={{
        width: 780,
        height: 420,
        borderRadius: 18,
        background: '#0b1218',
        border: `3px solid ${palette.paper}`,
        boxShadow: '24px 26px 0 rgba(0,0,0,0.22)',
        overflow: 'hidden',
      }}
    >
      <div style={{height: 58, borderBottom: '2px solid rgba(247,244,237,0.18)', display: 'flex', alignItems: 'center', gap: 12, paddingLeft: 22}}>
        {[palette.coral, palette.yellow, palette.green].map((color) => (
          <div key={color} style={{width: 17, height: 17, borderRadius: 999, background: color}} />
        ))}
      </div>
      <div style={{padding: 34, fontFamily: 'Consolas, Menlo, monospace'}}>
        {rows.map(([row, color], index) => {
          const opacity = interpolate(frame, [second(index * 0.36, fps), second(index * 0.36 + 0.24, fps)], [0, 1], {
            ...clamp,
            easing: ease,
          });
          return (
            <div key={row} style={{opacity, color, fontSize: 31, lineHeight: 1.65, fontWeight: 800}}>
              {row}
            </div>
          );
        })}
      </div>
    </div>
  );
};

const SceneOne = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const opacity = sceneFade(frame, fps, 3);

  return (
    <AbsoluteFill style={{opacity}}>
      <div style={{position: 'absolute', left: 160, top: 220, width: 650}}>
        <div style={{fontSize: 74, lineHeight: 1.08, fontWeight: 950, color: palette.paper, letterSpacing: 0}}>
          챙겨야 할 것들이
          <br />
          너무 많아서
        </div>
      </div>
      <AlertCard top={210} delay={0.1} color={palette.blue} title="경제 뉴스 42개" detail="읽어야 할 기사들이 쌓이는 중" />
      <AlertCard top={330} delay={0.45} color={palette.coral} title="수면 기록 없음" detail="어제 몇 시에 잤더라?" />
      <AlertCard top={450} delay={0.8} color={palette.yellow} title="영어 공부 기록 없음" detail="앱을 열어야만 남는 기록" />
      <AlertCard top={570} delay={1.15} color={palette.violet} title="메모할 것 3개" detail="머릿속에만 남아 있는 생각" />
      <Caption>매일 챙겨야 할 것들이 너무 많아서</Caption>
    </AbsoluteFill>
  );
};

const SceneTwo = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const opacity = sceneFade(frame, fps, 3);
  const glow = interpolate(frame, [0, second(1.4, fps)], [0, 1], {...clamp, easing: ease});

  return (
    <AbsoluteFill style={{opacity}}>
      <div style={{position: 'absolute', left: 210, top: 300, transform: `translateY(${rise(frame, fps, 0.1, 36)}px)`}}>
        <PiServer />
      </div>
      <div style={{position: 'absolute', left: 1020, top: 176, transform: `translateY(${rise(frame, fps, 0.4, 34)}px)`}}>
        <Phone compact>
          <div style={{paddingTop: 170, textAlign: 'center'}}>
            <div style={{margin: '0 auto', width: 112, height: 112, borderRadius: 999, background: `rgba(78,199,163,${0.18 + glow * 0.5})`, border: `4px solid ${palette.green}`}} />
            <div style={{marginTop: 34, fontSize: 32, fontWeight: 950, color: palette.ink}}>agent online</div>
            <div style={{marginTop: 12, fontSize: 22, fontWeight: 760, color: palette.muted}}>Telegram gateway connected</div>
          </div>
        </Phone>
      </div>
      <Caption>내 작은 서버에 비서를 하나 만들었다</Caption>
    </AbsoluteFill>
  );
};

const SceneThree = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const opacity = sceneFade(frame, fps, 6);

  return (
    <AbsoluteFill style={{opacity}}>
      <div style={{position: 'absolute', left: 132, top: 182, width: 610}}>
        <div style={{fontSize: 60, lineHeight: 1.12, fontWeight: 950, color: palette.paper}}>아침 경제 브리핑</div>
        <div style={{marginTop: 28, fontSize: 29, lineHeight: 1.45, fontWeight: 760, color: 'rgba(247,244,237,0.78)'}}>
          여러 뉴스 소스를 읽고, 오늘 볼 흐름만 텔레그램으로 정리합니다.
        </div>
      </div>
      <div style={{position: 'absolute', right: 220, top: 118, transform: `translateY(${rise(frame, fps, 0.1, 32)}px)`}}>
        <Phone>
          <Bubble delay={0.2}>{'오늘 아침 경제 브리핑입니다.'}</Bubble>
          <Bubble delay={0.7}>{'국내\n금리 인하 기대가 조정되며 채권 금리가 움직였습니다.'}</Bubble>
          <Bubble delay={1.25}>{'해외\n미국 고용 지표 둔화로 시장은 Fed 발언에 주목하고 있습니다.'}</Bubble>
          <Bubble delay={1.8}>{'오늘 볼 것\n환율, 국채 금리, 반도체 업종 흐름'}</Bubble>
        </Phone>
      </div>
      <Caption>아침과 저녁, 경제 뉴스는 핵심만 정리하고</Caption>
    </AbsoluteFill>
  );
};

const SceneFour = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const opacity = sceneFade(frame, fps, 6);

  return (
    <AbsoluteFill style={{opacity}}>
      <div style={{position: 'absolute', left: 126, top: 188, width: 650}}>
        <div style={{fontSize: 60, lineHeight: 1.12, fontWeight: 950, color: palette.paper}}>말하듯 남기는 기록</div>
        <div style={{marginTop: 28, fontSize: 29, lineHeight: 1.45, fontWeight: 760, color: 'rgba(247,244,237,0.78)'}}>
          수면, 공부, 메모를 별도 앱 입력 폼 없이 대화로 저장합니다.
        </div>
      </div>
      <div style={{position: 'absolute', right: 220, top: 118}}>
        <Phone>
          <Bubble from="me" delay={0.15}>
            어제 11시에 잤어
          </Bubble>
          <Bubble delay={0.65}>{'수면 기록을 저장했어요.\n2026-05-16 23:00'}</Bubble>
          <Bubble from="me" delay={1.35}>
            영어 30분 했어
          </Bubble>
          <Bubble delay={1.85}>영어공부 30분 기록 완료.</Bubble>
        </Phone>
      </div>
      <Caption>생활 기록은 앱을 열지 않고 말하듯 남긴다</Caption>
    </AbsoluteFill>
  );
};

const SceneFive = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const opacity = sceneFade(frame, fps, 5);

  return (
    <AbsoluteFill style={{opacity}}>
      <div style={{position: 'absolute', left: 132, top: 190, width: 650}}>
        <div style={{fontSize: 60, lineHeight: 1.12, fontWeight: 950, color: palette.paper}}>놓친 건 다시 챙기는 비서</div>
        <div style={{marginTop: 28, fontSize: 29, lineHeight: 1.45, fontWeight: 760, color: 'rgba(247,244,237,0.78)'}}>
          기록이 비어 있으면 조용히 묻고, 짧은 답으로 정리합니다.
        </div>
      </div>
      <div style={{position: 'absolute', right: 220, top: 118}}>
        <Phone>
          <Bubble delay={0.2}>{'오늘 수면 기록이 비어 있어요.\n어제 몇 시쯤 잤나요?'}</Bubble>
          <Bubble from="me" delay={1.1}>
            12시 반쯤
          </Bubble>
          <Bubble delay={1.7}>{'좋아요. 어제 수면 시작을\n00:30으로 기록했어요.'}</Bubble>
        </Phone>
      </div>
      <Caption>잊기 전에 묻고, 놓친 건 다시 챙긴다</Caption>
    </AbsoluteFill>
  );
};

const SceneSix = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const opacity = sceneFade(frame, fps, 4);

  return (
    <AbsoluteFill style={{opacity}}>
      <div style={{position: 'absolute', left: 146, top: 194, width: 620}}>
        <div style={{fontSize: 60, lineHeight: 1.12, fontWeight: 950, color: palette.paper}}>내 서버에서 돌아가는 AI</div>
        <div style={{marginTop: 28, fontSize: 29, lineHeight: 1.45, fontWeight: 760, color: 'rgba(247,244,237,0.78)'}}>
          상태 점검도, 저장소도, 게이트웨이도 직접 확인할 수 있게.
        </div>
      </div>
      <div style={{position: 'absolute', right: 170, top: 228, transform: `translateY(${rise(frame, fps, 0.05, 28)}px)`}}>
        <Terminal />
      </div>
      <Caption>클라우드 어딘가가 아니라, 내 서버에서</Caption>
    </AbsoluteFill>
  );
};

const SceneSeven = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const opacity = interpolate(frame, [0, second(0.5, fps)], [0, 1], {...clamp, easing: ease});
  const scale = interpolate(frame, [0, second(2, fps)], [0.96, 1], {...clamp, easing: ease});

  return (
    <AbsoluteFill style={{opacity}}>
      <div style={{position: 'absolute', left: 170, top: 280, transform: `scale(${scale})`, transformOrigin: 'left center'}}>
        <div style={{fontSize: 98, lineHeight: 1, fontWeight: 950, color: palette.paper, letterSpacing: 0}}>my-nanobot-rpi</div>
        <div style={{marginTop: 30, fontSize: 46, lineHeight: 1.2, fontWeight: 860, color: 'rgba(247,244,237,0.82)'}}>나만의 인공지능 비서</div>
        <div style={{marginTop: 64, fontSize: 30, fontWeight: 800, color: palette.green}}>github.com/msaltnet/my-nanobot-rpi</div>
      </div>
      <div style={{position: 'absolute', right: 170, top: 306, transform: `translateY(${rise(frame, fps, 0.2, 26)}px)`}}>
        <PiServer />
      </div>
    </AbsoluteFill>
  );
};

export const NanobotIntro = () => {
  const {fps} = useVideoConfig();

  return (
    <Stage>
      <Sequence from={0} durationInFrames={second(3, fps)}>
        <SceneOne />
      </Sequence>
      <Sequence from={second(3, fps)} durationInFrames={second(3, fps)}>
        <SceneTwo />
      </Sequence>
      <Sequence from={second(6, fps)} durationInFrames={second(6, fps)}>
        <SceneThree />
      </Sequence>
      <Sequence from={second(12, fps)} durationInFrames={second(6, fps)}>
        <SceneFour />
      </Sequence>
      <Sequence from={second(18, fps)} durationInFrames={second(5, fps)}>
        <SceneFive />
      </Sequence>
      <Sequence from={second(23, fps)} durationInFrames={second(4, fps)}>
        <SceneSix />
      </Sequence>
      <Sequence from={second(27, fps)} durationInFrames={second(3, fps)}>
        <SceneSeven />
      </Sequence>
    </Stage>
  );
};

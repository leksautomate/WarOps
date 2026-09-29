import React from 'react';
import {
  AbsoluteFill,
  Audio,
  Img,
  interpolate,
  Sequence,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

// ---------------------------------------------------------------------------
// Overlay templates — the "data documentary" graphic-card style:
// giant stat numerals, date cards, timelines, bar charts, data tables,
// portrait dossiers, split comparisons, quotes, numbered lists, and
// ruler diagrams. Rendered on a near-black plate, or — with overImage —
// floating over the segment's archival photo dimmed with black; the AI
// overlay director (OVERLAY_DIRECTOR.md) picks one template per
// narration segment based on the script.
//
// MOTION LANGUAGE (studied frame-by-frame from reference footage):
// - Hard cuts everywhere. Elements snap in, staged 0.2-0.4s apart.
//   No fades, dissolves, slides, or rises on text.
// - Hero numbers use the odometer: digits roll vertically at constant
//   speed like a slot machine, RED while rolling, dead stop on the
//   final WHITE number. ~1s for 2 digits, ~2-3s for 4+ digits.
// - Table/list rows appear one by one, top to bottom, ~0.3s apart.
// - Bars and rulers fill/draw left to right at constant speed.
// - Timeline blocks light up left to right at constant speed.
// - Photos are static. No Ken Burns on cards.
// - Text never types in letter by letter. Nothing bounces or eases.
// ---------------------------------------------------------------------------

export type OverlaySpec =
  | {
      type: 'stat';
      kicker?: string;
      value: number;
      prefix?: string;
      suffix?: string;
      label: string;
      source?: string;
    } & WithCue
  | ({type: 'date'; date: string; sub?: string} & WithCue)
  | {
      type: 'timeline';
      kicker: string;
      startLabel: string;
      endLabel: string;
      blocks: number;
      value: number;
      prefix?: string;
      suffix?: string;
      label: string;
    } & WithCue
  | ({type: 'bars'; title: string; items: {label: string; pct: number}[]} & WithCue)
  | {
      type: 'table';
      title: string;
      stamp?: string;
      head: [string, string];
      rows: [string, string | number][];
      total?: string | number;
    } & WithCue
  | {
      type: 'portrait';
      image: string; // path under public/, e.g. "images/portrait_04_0.jpg"
      rank?: string;
      name: string;
      role?: string;
      fate?: string;
      fateTone?: 'red' | 'muted';
    } & WithCue
  | {
      type: 'split';
      left: {stat: string | number; label: string};
      right: {stat: string | number; label: string};
      note?: string;
    } & WithCue
  | ({type: 'quote'; text: string; by?: string} & WithCue)
  | {
      type: 'list';
      kicker?: string;
      items: {no: string; title: string; sub?: string}[];
      note?: string;
    } & WithCue
  | {
      type: 'diagram';
      kicker?: string;
      value: number;
      prefix?: string;
      suffix?: string;
      label: string;
      scale: [number, number]; // [from, to] for the ruler
      marker?: number; // highlighted tick, e.g. 25 on a 0-30 ruler
      unit?: string;
      note?: string;
      image?: string; // optional photo inset under public/
    } & WithCue
  // -- added 2026-09-27 from the reference-video teardown --
  | {
      type: 'year-axis';
      startYear: number;
      endYear: number;
      targetYear: number;
      label?: string; // kicker above, e.g. "THE WAR IN EUROPE"
    } & WithCue
  | {
      type: 'map-callout';
      location: string; // place name, e.g. "Hammelburg, Germany"
      label: string; // callout text, e.g. "Oflag 13B Prison Camp"
      mapImage: string; // path under public/, fetched by scripts/fetch_map.py
      note?: string;
    } & WithCue
  | ({type: 'question'; text: string; sub?: string} & WithCue)
  | ({type: 'bold-word'; word: string; sub?: string} & WithCue)
  | {
      type: 'checklist';
      title: string;
      items: {label: string; value: string}[];
      note?: string;
    } & WithCue
  | {
      type: 'wiki-quote';
      article: string; // Wikipedia article title, e.g. "Battle of Arracourt"
      highlight: string; // exact phrase highlighted in the article text
      image: string; // path under public/, fetched by scripts/wiki_shot.py
    } & WithCue;

// cue: a distinctive phrase from the segment's narration (2-8 words).
// The card pops in as those words are spoken, so the card always
// matches the speech instead of just decorating the segment. The
// renderer converts the phrase's character offset to a time fraction
// (same approximation as portrait timing) and starts the card a beat
// before the words land. Omit it and the card pops in ~0.4s after
// the scene starts, as before.
type WithCue = {
  cue?: string;
  // background treatment while the card is up (Frontier 5.1 plays blurred
  // own-footage behind cards): 'dim' (default) darkens the scene photo,
  // 'blur' swaps in a blurred copy of the scene photo behind the card.
  bgEffect?: 'dim' | 'blur';
};

const BG = '#0b0b0d';
const INK = '#f4f4f5';
const MUTED = '#8f8f96';
const RED = '#b3372f';
const BAR_RED = '#c14a35';
const MONO = "'Courier New', ui-monospace, SFMono-Regular, monospace";
const HEAVY = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif";
const SERIF = "Georgia, 'Times New Roman', serif";

const useVertical = () => {
  const {width, height} = useVideoConfig();
  return height > width;
};

const fmt = (v: number) => Math.round(v).toLocaleString('en-US');

// directors sometimes hand us raw numbers where a formatted string would do;
// commas keep giant figures readable.
const fmtAny = (v: string | number) =>
  typeof v === 'number' ? fmt(v) : v;

// ---------------------------------------------------------------------------
// Hard-cut staging: the element is in the layout from frame 0 but invisible,
// then snaps in at `start`. No fade, no slide.
// ---------------------------------------------------------------------------
const Cut: React.FC<{
  start?: number;
  children: React.ReactNode;
  style?: React.CSSProperties;
}> = ({start = 0, children, style}) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        width: '100%',
        visibility: frame >= start ? 'visible' : 'hidden',
        ...style,
      }}
    >
      {children}
    </div>
  );
};

const Kicker: React.FC<{children: React.ReactNode; size?: number}> = ({
  children,
  size = 30,
}) => (
  <div
    style={{
      fontFamily: MONO,
      fontSize: size,
      letterSpacing: 7,
      color: MUTED,
      textTransform: 'uppercase',
    }}
  >
    {children}
  </div>
);

// ---------------------------------------------------------------------------
// Odometer: slot-machine rolling digits. Constant (linear) velocity, RED
// while rolling, dead stop on the final WHITE number. Non-digit characters
// (commas, spaces) stay static. Before `start` the final number sits in the
// layout invisibly so nothing jumps when the roll begins.
// ---------------------------------------------------------------------------
const ROLL_REPEATS = 4;

const RollingDigit: React.FC<{
  digit: number;
  start: number;
  frames: number;
  cell: number;
  rolling: boolean;
}> = ({digit, start, frames, cell, rolling}) => {
  const frame = useCurrentFrame();
  if (!rolling || frame >= start + frames) {
    return (
      <span
        style={{
          display: 'inline-block',
          width: '0.62em',
          textAlign: 'center',
        }}
      >
        {digit}
      </span>
    );
  }
  const p = (frame - start) / frames; // linear: constant velocity
  const finalIdx = (ROLL_REPEATS - 1) * 10 + digit;
  // Rolling window: only 4 cells are ever rendered; the digits they show
  // are reassigned as the roll progresses, so the strip offset stays small
  // (a huge translated strip mis-rasterizes in Chromium).
  const vIdx = p * finalIdx;
  const topVirtual = Math.floor(vIdx) - 1;
  const offset = -(vIdx - topVirtual) * cell;
  const vdigit = (v: number) => ((v % 10) + 10) % 10;
  return (
    <div
      style={{
        display: 'inline-block',
        position: 'relative',
        width: '0.62em',
        height: cell,
        overflow: 'hidden',
        verticalAlign: 'top',
      }}
    >
      <div
        style={{
          position: 'absolute',
          left: 0,
          top: offset,
          width: '100%',
          color: RED,
          fontSize: cell,
          lineHeight: 1,
        }}
      >
        {[0, 1, 2, 3].map((k) => (
          <div
            key={k}
            style={{
              height: '1em',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            {vdigit(topVirtual + k)}
          </div>
        ))}
      </div>
    </div>
  );
};

const Odometer: React.FC<{
  value: number;
  start?: number;
  fontSize: number;
  prefix?: string;
  suffix?: string;
  settledColor?: string;
  maxFrames?: number; // cap the roll so it always settles inside a short card window
}> = ({value, start = 0, fontSize, prefix, suffix, settledColor = INK, maxFrames}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const text = fmt(value);
  const digits = text.replace(/\D/g, '').length;
  // ~1s for 2 digits, ~2-3s for 4+ digits
  let frames = Math.max(12, Math.round((0.4 + 0.45 * digits) * fps));
  if (maxFrames != null) frames = Math.min(frames, Math.max(12, maxFrames));
  const cell = Math.round(fontSize * 1.02);
  const rolling = frame >= start && frame < start + frames;
  return (
    <span
      style={{
        fontFamily: HEAVY,
        fontWeight: 900,
        fontSize,
        lineHeight: 1,
        letterSpacing: -2,
        color: settledColor,
        fontVariantNumeric: 'tabular-nums',
        whiteSpace: 'nowrap',
        opacity: frame >= start ? 1 : 0,
      }}
    >
      {prefix ?? ''}
      {[...text].map((ch, i) =>
        /\d/.test(ch) ? (
          <RollingDigit
            key={i}
            digit={Number(ch)}
            start={start}
            frames={frames}
            cell={cell}
            rolling={rolling}
          />
        ) : (
          <span key={i}>{ch}</span>
        )
      )}
      {suffix ?? ''}
    </span>
  );
};

// --- STAT: kicker / giant odometer number / label / source line -----------
const StatOverlay: React.FC<{
  spec: Extract<OverlaySpec, {type: 'stat'}>;
  durationInFrames: number;
  overImage?: boolean;
}> = ({spec, durationInFrames, overImage}) => {
  const vertical = useVertical();
  return (
    <AbsoluteFill
      style={{
        backgroundColor: overImage ? 'transparent' : BG,
        justifyContent: 'center',
        alignItems: 'center',
        padding: vertical ? 70 : 90,
      }}
    >
      <div style={{textAlign: 'center', width: '100%'}}>
        {spec.kicker ? (
          <Cut>
            <Kicker size={vertical ? 34 : 30}>{spec.kicker}</Kicker>
          </Cut>
        ) : null}
        <div style={{margin: '26px 0 18px 0'}}>
          <Odometer
            value={spec.value}
            start={5}
            fontSize={vertical ? 150 : 190}
            prefix={spec.prefix}
            suffix={spec.suffix}
            maxFrames={durationInFrames - 5 - 30}
          />
        </div>
        <Cut start={8}>
          <div
            style={{
              fontFamily: MONO,
              fontSize: vertical ? 38 : 34,
              letterSpacing: 6,
              color: INK,
              textTransform: 'uppercase',
            }}
          >
            {spec.label}
          </div>
        </Cut>
        {spec.source ? (
          <Cut start={16}>
            <div
              style={{
                marginTop: 34,
                fontFamily: MONO,
                fontSize: 24,
                letterSpacing: 4,
                color: MUTED,
                textTransform: 'uppercase',
              }}
            >
              {spec.source}
            </div>
          </Cut>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

// --- DATE: giant date, rule, sub-line --------------------------------------
const DateOverlay: React.FC<{
  spec: Extract<OverlaySpec, {type: 'date'}>;
  overImage?: boolean;
}> = ({spec, overImage}) => {
  const vertical = useVertical();
  return (
    <AbsoluteFill
      style={{
        backgroundColor: overImage ? 'transparent' : BG,
        justifyContent: 'center',
        paddingLeft: vertical ? 70 : 130,
        paddingRight: vertical ? 70 : 130,
      }}
    >
      <div style={{width: '100%'}}>
        <Cut>
          <div
            style={{
              fontFamily: HEAVY,
              fontWeight: 900,
              fontSize: vertical ? 118 : 150,
              color: INK,
              letterSpacing: 4,
              lineHeight: 1.05,
            }}
          >
            {spec.date}
          </div>
        </Cut>
        <Cut start={4}>
          <div
            style={{
              width: '100%',
              height: 4,
              backgroundColor: INK,
              margin: '34px 0',
              opacity: 0.9,
            }}
          />
        </Cut>
        {spec.sub ? (
          <Cut start={7}>
            <div
              style={{
                fontFamily: MONO,
                fontSize: vertical ? 34 : 36,
                letterSpacing: 5,
                color: INK,
                textTransform: 'uppercase',
                lineHeight: 1.6,
              }}
            >
              {spec.sub}
            </div>
          </Cut>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

// --- TIMELINE: kicker, start/end labels, filling block bar, odometer ------
const TimelineOverlay: React.FC<{
  spec: Extract<OverlaySpec, {type: 'timeline'}>;
  durationInFrames: number;
  overImage?: boolean;
}> = ({spec, durationInFrames, overImage}) => {
  const frame = useCurrentFrame();
  const vertical = useVertical();
  const blocks = Math.max(4, Math.min(40, spec.blocks));
  // constant-speed fill across most of the card's screen time
  const fillT = interpolate(frame, [4, Math.max(20, durationInFrames - 30)], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const lit = Math.floor(fillT * blocks);
  return (
    <AbsoluteFill
      style={{
        backgroundColor: overImage ? 'transparent' : BG,
        justifyContent: 'center',
        alignItems: 'center',
        padding: vertical ? 60 : 110,
      }}
    >
      <div style={{width: '100%', maxWidth: vertical ? '100%' : 1200}}>
        <Cut>
          <Kicker size={vertical ? 32 : 30}>{spec.kicker}</Kicker>
        </Cut>
        <Cut>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              marginTop: 26,
              fontFamily: MONO,
              fontSize: 26,
              letterSpacing: 4,
              color: MUTED,
            }}
          >
            <span>{spec.startLabel}</span>
            <span>{spec.endLabel}</span>
          </div>
        </Cut>
        <div style={{display: 'flex', gap: 6, marginTop: 14}}>
          {Array.from({length: blocks}).map((_, i) => (
            <div
              key={i}
              style={{
                flex: 1,
                height: 18,
                backgroundColor: i < lit ? INK : 'rgba(255,255,255,0.14)',
              }}
            />
          ))}
        </div>
        <Cut start={12}>
          <div
            style={{
              width: '60%',
              height: 2,
              backgroundColor: 'rgba(255,255,255,0.25)',
              margin: '54px auto',
            }}
          />
        </Cut>
        <div style={{textAlign: 'center'}}>
          <Cut start={14}>
            <div
              style={{
                fontFamily: MONO,
                fontSize: vertical ? 36 : 34,
                letterSpacing: 6,
                color: INK,
                textTransform: 'uppercase',
              }}
            >
              {spec.label}
            </div>
          </Cut>
          <div style={{marginTop: 18}}>
            <Odometer
              value={spec.value}
              start={18}
              fontSize={vertical ? 150 : 170}
              prefix={spec.prefix}
              suffix={spec.suffix}
              maxFrames={durationInFrames - 18 - 30}
            />
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

// --- BARS: title + horizontal percentage bars (constant-speed fill) -------
const BarsOverlay: React.FC<{
  spec: Extract<OverlaySpec, {type: 'bars'}>;
  overImage?: boolean;
}> = ({spec, overImage}) => {
  const frame = useCurrentFrame();
  const vertical = useVertical();
  const FILL = 36; // ~1.2s constant-speed fill
  return (
    <AbsoluteFill
      style={{
        backgroundColor: overImage ? 'transparent' : BG,
        justifyContent: 'center',
        paddingLeft: vertical ? 60 : 130,
        paddingRight: vertical ? 60 : 130,
      }}
    >
      <div style={{width: '100%'}}>
        <Cut>
          <div
            style={{
              fontFamily: MONO,
              fontSize: vertical ? 34 : 32,
              letterSpacing: 5,
              color: MUTED,
              textTransform: 'uppercase',
              marginBottom: vertical ? 70 : 60,
            }}
          >
            {spec.title}
          </div>
        </Cut>
        {spec.items.map((item, i) => {
          const s = 6 + i * 9; // stagger ~0.3s
          const w = interpolate(
            frame,
            [s, s + FILL],
            [0, Math.max(0, Math.min(100, item.pct))],
            {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}
          );
          return (
            <Cut key={i} start={s}>
              <div style={{marginBottom: vertical ? 64 : 54}}>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'baseline',
                    justifyContent: 'space-between',
                  }}
                >
                  <span
                    style={{
                      fontFamily: HEAVY,
                      fontWeight: 800,
                      fontSize: vertical ? 46 : 40,
                      letterSpacing: 3,
                      color: INK,
                    }}
                  >
                    {item.label}
                  </span>
                  <span
                    style={{
                      fontFamily: HEAVY,
                      fontWeight: 900,
                      fontSize: vertical ? 84 : 76,
                      color: INK,
                    }}
                  >
                    {Math.round(item.pct)}%
                  </span>
                </div>
                <div
                  style={{
                    marginTop: 14,
                    height: 26,
                    backgroundColor: 'rgba(255,255,255,0.10)',
                    position: 'relative',
                  }}
                >
                  <div
                    style={{
                      position: 'absolute',
                      left: 0,
                      top: 0,
                      bottom: 0,
                      width: `${w}%`,
                      backgroundColor: BAR_RED,
                    }}
                  />
                </div>
              </div>
            </Cut>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

// --- TABLE: ledger of name -> figure rows + odometer total ----------------
const TableOverlay: React.FC<{
  spec: Extract<OverlaySpec, {type: 'table'}>;
  durationInFrames: number;
  overImage?: boolean;
}> = ({spec, durationInFrames, overImage}) => {
  const frame = useCurrentFrame();
  const vertical = useVertical();
  const totalStart = 12 + spec.rows.length * 9;
  return (
    <AbsoluteFill
      style={{
        backgroundColor: overImage ? 'transparent' : BG,
        justifyContent: 'center',
        paddingLeft: vertical ? 56 : 150,
        paddingRight: vertical ? 56 : 150,
      }}
    >
      <div style={{width: '100%', position: 'relative'}}>
        {spec.stamp ? (
          <div
            style={{
              position: 'absolute',
              top: -90,
              right: 0,
              border: `4px solid ${RED}`,
              color: RED,
              fontFamily: MONO,
              fontSize: 26,
              letterSpacing: 4,
              padding: '12px 22px',
              transform: 'rotate(-4deg)',
              textTransform: 'uppercase',
              visibility: frame >= 20 ? 'visible' : 'hidden',
            }}
          >
            {spec.stamp}
          </div>
        ) : null}
        <Cut>
          <div
            style={{
              fontFamily: MONO,
              fontSize: vertical ? 36 : 34,
              letterSpacing: 6,
              color: INK,
              textTransform: 'uppercase',
              borderBottom: '2px solid rgba(255,255,255,0.35)',
              paddingBottom: 18,
              marginBottom: 34,
            }}
          >
            {spec.title}
          </div>
        </Cut>
        <Cut start={4}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              fontFamily: MONO,
              fontSize: 24,
              letterSpacing: 5,
              color: MUTED,
              textTransform: 'uppercase',
              marginBottom: 26,
            }}
          >
            <span>{spec.head[0]}</span>
            <span>{spec.head[1]}</span>
          </div>
        </Cut>
        {spec.rows.map((row, i) => (
          <Cut key={i} start={8 + i * 9}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'baseline',
                padding: '20px 0',
                borderBottom: '1px solid rgba(255,255,255,0.08)',
              }}
            >
              <span
                style={{
                  fontFamily: MONO,
                  fontSize: vertical ? 40 : 38,
                  letterSpacing: 4,
                  color: INK,
                }}
              >
                {row[0]}
              </span>
              <span
                style={{
                  fontFamily: MONO,
                  fontSize: vertical ? 40 : 38,
                  letterSpacing: 2,
                  color: RED,
                }}
              >
                {fmtAny(row[1])}
              </span>
            </div>
          </Cut>
        ))}
        {spec.total != null && spec.total !== '' ? (
          <Cut start={totalStart}>
            <div
              style={{
                marginTop: 40,
                borderTop: '3px solid rgba(255,255,255,0.6)',
                paddingTop: 30,
              }}
            >
              {typeof spec.total === 'number' ? (
                <Odometer
                  value={spec.total}
                  start={totalStart + 2}
                  fontSize={vertical ? 120 : 130}
                  maxFrames={durationInFrames - (totalStart + 2) - 30}
                />
              ) : (
                <div
                  style={{
                    fontFamily: HEAVY,
                    fontWeight: 900,
                    fontSize: vertical ? 120 : 130,
                    color: INK,
                    letterSpacing: 2,
                    lineHeight: 1,
                  }}
                >
                  {spec.total}
                </div>
              )}
            </div>
          </Cut>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

// --- PORTRAIT: framed photo + rank / name / role / fate ------------------
// Reference: text snaps in; the photo fades in quickly. Photo stays static.
const PortraitCardOverlay: React.FC<{
  spec: Extract<OverlaySpec, {type: 'portrait'}>;
  overImage?: boolean;
}> = ({spec, overImage}) => {
  const frame = useCurrentFrame();
  const vertical = useVertical();
  const photoW = vertical ? 460 : 480;
  const photoH = Math.round(photoW * 1.28);
  const photoO = interpolate(frame, [6, 14], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const body = (
    <>
      {spec.rank ? (
        <Cut>
          <Kicker size={vertical ? 32 : 28}>{spec.rank}</Kicker>
        </Cut>
      ) : null}
      <Cut start={4}>
        <div
          style={{
            fontFamily: HEAVY,
            fontWeight: 900,
            fontSize: vertical ? 92 : 96,
            color: INK,
            lineHeight: 1.04,
            margin: '22px 0',
            letterSpacing: 1,
          }}
        >
          {spec.name}
        </div>
      </Cut>
      {spec.role ? (
        <Cut start={8}>
          <div
            style={{
              fontFamily: HEAVY,
              fontWeight: 400,
              fontSize: vertical ? 40 : 36,
              color: MUTED,
              letterSpacing: 1,
            }}
          >
            {spec.role}
          </div>
        </Cut>
      ) : null}
      {spec.fate ? (
        <Cut start={12}>
          <div
            style={{
              width: '100%',
              height: 2,
              backgroundColor: 'rgba(255,255,255,0.25)',
              margin: '34px 0',
            }}
          />
          <div
            style={{
              fontFamily: MONO,
              fontSize: vertical ? 36 : 32,
              letterSpacing: 6,
              color: spec.fateTone === 'muted' ? MUTED : RED,
              textTransform: 'uppercase',
            }}
          >
            {spec.fate}
          </div>
        </Cut>
      ) : null}
    </>
  );
  return (
    <AbsoluteFill
      style={{
        backgroundColor: overImage ? 'transparent' : BG,
        justifyContent: 'center',
        alignItems: 'center',
        padding: vertical ? 60 : 110,
      }}
    >
      <div
        style={{
          display: 'flex',
          flexDirection: vertical ? 'column' : 'row',
          alignItems: 'center',
          gap: vertical ? 54 : 90,
          width: '100%',
          justifyContent: 'center',
        }}
      >
        <div
          style={{
            border: '2px solid rgba(255,255,255,0.35)',
            padding: 14,
            backgroundColor: '#101013',
            boxShadow: '0 24px 70px rgba(0,0,0,0.6)',
            flexShrink: 0,
            opacity: photoO,
            visibility: frame >= 6 ? 'visible' : 'hidden',
          }}
        >
          <Img
            src={staticFile(spec.image)}
            style={{
              width: photoW,
              height: photoH,
              objectFit: 'cover',
              display: 'block',
              filter: 'grayscale(1) contrast(1.05)',
            }}
          />
        </div>
        <div
          style={{
            textAlign: vertical ? 'center' : 'left',
            maxWidth: vertical ? '100%' : 760,
          }}
        >
          {body}
        </div>
      </div>
    </AbsoluteFill>
  );
};

// --- SPLIT: two stats side by side (or stacked) with a divider -----------
const SplitOverlay: React.FC<{
  spec: Extract<OverlaySpec, {type: 'split'}>;
  overImage?: boolean;
}> = ({spec, overImage}) => {
  const vertical = useVertical();
  const panel = (s: {stat: string | number; label: string}) => (
    <div style={{flex: 1, textAlign: 'center', padding: vertical ? 30 : 40}}>
      <div
        style={{
          fontFamily: HEAVY,
          fontWeight: 900,
          fontSize: vertical ? 120 : 130,
          color: INK,
          lineHeight: 1,
          letterSpacing: -1,
        }}
      >
        {fmtAny(s.stat)}
      </div>
      <div
        style={{
          marginTop: 22,
          fontFamily: MONO,
          fontSize: vertical ? 36 : 32,
          letterSpacing: 6,
          color: INK,
          textTransform: 'uppercase',
        }}
      >
        {s.label}
      </div>
    </div>
  );
  return (
    <AbsoluteFill
      style={{
        backgroundColor: overImage ? 'transparent' : BG,
        justifyContent: 'center',
        alignItems: 'center',
        padding: vertical ? 50 : 80,
      }}
    >
      <div style={{width: '100%'}}>
        <div
          style={{
            display: 'flex',
            flexDirection: vertical ? 'column' : 'row',
            alignItems: 'stretch',
          }}
        >
          <Cut>{panel(spec.left)}</Cut>
          <Cut start={5}>
            <div
              style={
                vertical
                  ? {
                      height: 3,
                      backgroundColor: 'rgba(255,255,255,0.7)',
                      margin: '30px 60px',
                    }
                  : {width: 3, backgroundColor: 'rgba(255,255,255,0.7)'}
              }
            />
          </Cut>
          <Cut start={9}>{panel(spec.right)}</Cut>
        </div>
        {spec.note ? (
          <Cut start={15}>
            <div
              style={{
                marginTop: 44,
                textAlign: 'center',
                fontFamily: MONO,
                fontSize: 24,
                letterSpacing: 4,
                color: MUTED,
                textTransform: 'uppercase',
              }}
            >
              {spec.note}
            </div>
          </Cut>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

// --- QUOTE: giant serif pull-quote ---------------------------------------
const QuoteOverlay: React.FC<{
  spec: Extract<OverlaySpec, {type: 'quote'}>;
  overImage?: boolean;
}> = ({spec, overImage}) => {
  const vertical = useVertical();
  return (
    <AbsoluteFill
      style={{
        backgroundColor: overImage ? 'transparent' : BG,
        justifyContent: 'center',
        paddingLeft: vertical ? 70 : 150,
        paddingRight: vertical ? 70 : 150,
      }}
    >
      <div style={{width: '100%'}}>
        <Cut>
          <div
            style={{
              fontFamily: SERIF,
              fontSize: vertical ? 76 : 88,
              color: INK,
              lineHeight: 1.35,
            }}
          >
            <span style={{color: RED}}>&ldquo;</span>
            {spec.text}
            <span style={{color: RED}}>&rdquo;</span>
          </div>
        </Cut>
        {spec.by ? (
          <Cut start={9}>
            <div
              style={{
                marginTop: 44,
                fontFamily: MONO,
                fontSize: vertical ? 34 : 32,
                letterSpacing: 6,
                color: MUTED,
                textTransform: 'uppercase',
              }}
            >
              — {spec.by}
            </div>
          </Cut>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

// --- LIST: numbered items (e.g. "01 / 1ST SHOCK ARMY / DID NOT EXIST") ----
const ListOverlay: React.FC<{
  spec: Extract<OverlaySpec, {type: 'list'}>;
  overImage?: boolean;
}> = ({spec, overImage}) => {
  const vertical = useVertical();
  return (
    <AbsoluteFill
      style={{
        backgroundColor: overImage ? 'transparent' : BG,
        justifyContent: 'center',
        paddingLeft: vertical ? 60 : 130,
        paddingRight: vertical ? 60 : 130,
      }}
    >
      <div style={{width: '100%'}}>
        {spec.kicker ? (
          <Cut>
            <div style={{marginBottom: 50}}>
              <Kicker size={vertical ? 34 : 32}>{spec.kicker}</Kicker>
            </div>
          </Cut>
        ) : null}
        {spec.items.map((item, i) => (
          <Cut key={i} start={6 + i * 9}>
            <div
              style={{
                display: 'flex',
                alignItems: 'baseline',
                gap: vertical ? 30 : 40,
                padding: '26px 0',
                borderBottom: '1px solid rgba(255,255,255,0.10)',
              }}
            >
              <span
                style={{
                  fontFamily: MONO,
                  fontWeight: 700,
                  fontSize: vertical ? 56 : 60,
                  color: RED,
                  letterSpacing: 2,
                  flexShrink: 0,
                }}
              >
                {item.no}
              </span>
              <span>
                <span
                  style={{
                    display: 'block',
                    fontFamily: HEAVY,
                    fontWeight: 800,
                    fontSize: vertical ? 52 : 54,
                    color: INK,
                    letterSpacing: 2,
                    lineHeight: 1.15,
                  }}
                >
                  {item.title}
                </span>
                {item.sub ? (
                  <span
                    style={{
                      display: 'block',
                      marginTop: 10,
                      fontFamily: MONO,
                      fontSize: vertical ? 34 : 30,
                      letterSpacing: 4,
                      color: MUTED,
                      textTransform: 'uppercase',
                    }}
                  >
                    {item.sub}
                  </span>
                ) : null}
              </span>
            </div>
          </Cut>
        ))}
        {spec.note ? (
          <Cut start={10 + spec.items.length * 9}>
            <div
              style={{
                marginTop: 44,
                fontFamily: MONO,
                fontSize: 26,
                letterSpacing: 4,
                color: MUTED,
                textTransform: 'uppercase',
              }}
            >
              {spec.note}
            </div>
          </Cut>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

// --- DIAGRAM: hero odometer + ruler that draws left to right + photo -----
const DiagramOverlay: React.FC<{
  spec: Extract<OverlaySpec, {type: 'diagram'}>;
  durationInFrames: number;
  overImage?: boolean;
}> = ({spec, durationInFrames, overImage}) => {
  const frame = useCurrentFrame();
  const vertical = useVertical();
  const [from, to] = spec.scale;
  const span = Math.max(1, to - from);
  const DRAW = 40; // ~1.3s constant-speed draw
  const drawStart = 12;
  const p = interpolate(frame, [drawStart, drawStart + DRAW], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const TICKS = 10;
  const tickAt = (t: number) => from + (span * t) / TICKS;
  const markerFrac =
    spec.marker != null ? (spec.marker - from) / span : null;
  const photoW = vertical ? 420 : 400;
  const photoH = Math.round(photoW * 0.72);
  const textBlock = (
    <div style={{width: '100%'}}>
      {spec.kicker ? (
        <Cut>
          <Kicker size={vertical ? 32 : 30}>{spec.kicker}</Kicker>
        </Cut>
      ) : null}
      <div style={{margin: '24px 0 14px 0'}}>
        <Odometer
          value={spec.value}
          start={5}
          fontSize={vertical ? 150 : 170}
          prefix={spec.prefix}
          suffix={spec.suffix}
          maxFrames={durationInFrames - 5 - 30}
        />
      </div>
      <Cut start={8}>
        <div
          style={{
            fontFamily: MONO,
            fontSize: vertical ? 36 : 32,
            letterSpacing: 6,
            color: INK,
            textTransform: 'uppercase',
          }}
        >
          {spec.label}
        </div>
      </Cut>
      {/* ruler: line wipes left to right; ticks snap in as it passes */}
      <div style={{marginTop: vertical ? 60 : 54, position: 'relative', height: 96}}>
        <div
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            top: 40,
            height: 4,
            backgroundColor: 'rgba(255,255,255,0.15)',
          }}
        />
        <div
          style={{
            position: 'absolute',
            left: 0,
            top: 40,
            height: 4,
            width: `${p * 100}%`,
            backgroundColor: INK,
          }}
        />
        {Array.from({length: TICKS + 1}).map((_, t) => {
          const frac = t / TICKS;
          const isMarker =
            markerFrac != null && Math.abs(frac - markerFrac) < 0.5 / TICKS;
          const vis = frame >= drawStart && p >= frac;
          return (
            <div
              key={t}
              style={{
                position: 'absolute',
                left: `${frac * 100}%`,
                top: isMarker ? 22 : 30,
                width: isMarker ? 5 : 3,
                height: isMarker ? 44 : 26,
                backgroundColor: isMarker ? RED : INK,
                transform: 'translateX(-50%)',
                visibility: vis ? 'visible' : 'hidden',
              }}
            />
          );
        })}
        {[0, 0.5, 1].map((frac) => {
          const vis = frame >= drawStart && p >= frac;
          const anchor =
            frac === 0
              ? {left: 0, transform: 'none'}
              : frac === 1
                ? {left: 'auto' as const, right: 0, transform: 'none'}
                : {left: `${frac * 100}%`, transform: 'translateX(-50%)'};
          return (
            <div
              key={frac}
              style={{
                position: 'absolute',
                top: 74,
                fontFamily: MONO,
                fontSize: 26,
                letterSpacing: 3,
                color: MUTED,
                visibility: vis ? 'visible' : 'hidden',
                whiteSpace: 'nowrap',
                ...anchor,
              }}
            >
              {fmt(tickAt(frac * TICKS))}
              {frac === 1 && spec.unit ? ` ${spec.unit}` : ''}
            </div>
          );
        })}
      </div>
      {spec.note ? (
        <Cut start={drawStart + DRAW + 6}>
          <div
            style={{
              marginTop: 44,
              fontFamily: MONO,
              fontSize: 26,
              letterSpacing: 4,
              color: MUTED,
              textTransform: 'uppercase',
              lineHeight: 1.7,
            }}
          >
            {spec.note}
          </div>
        </Cut>
      ) : null}
    </div>
  );
  return (
    <AbsoluteFill
      style={{
        backgroundColor: overImage ? 'transparent' : BG,
        justifyContent: 'center',
        alignItems: 'center',
        padding: vertical ? 60 : 110,
      }}
    >
      <div
        style={{
          width: '100%',
          display: 'flex',
          flexDirection: vertical ? 'column' : 'row',
          alignItems: 'center',
          gap: vertical ? 50 : 80,
        }}
      >
        <div style={{flex: 1, width: '100%'}}>{textBlock}</div>
        {spec.image ? (
          <div
            style={{
              border: '2px solid rgba(255,255,255,0.35)',
              padding: 12,
              backgroundColor: '#101013',
              boxShadow: '0 24px 70px rgba(0,0,0,0.6)',
              flexShrink: 0,
              visibility: frame >= drawStart + 10 ? 'visible' : 'hidden',
            }}
          >
            <Img
              src={staticFile(spec.image)}
              style={{
                width: photoW,
                height: photoH,
                objectFit: 'cover',
                display: 'block',
                filter: 'grayscale(1) contrast(1.05)',
              }}
            />
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// YearAxis: a year bar (startYear → endYear) with a marker that sweeps at
// constant speed and dead-stops on targetYear. The reference video opens
// with exactly this (1939–1951 landing on 1945).
// ---------------------------------------------------------------------------
const YearAxisOverlay: React.FC<{
  spec: Extract<OverlaySpec, {type: 'year-axis'}>;
  overImage?: boolean;
}> = ({spec, overImage}) => {
  const frame = useCurrentFrame();
  const vertical = useVertical();
  const frac =
    (spec.targetYear - spec.startYear) /
    Math.max(1, spec.endYear - spec.startYear);
  // marker sweep: constant speed, dead stop (motion language)
  const sweep = interpolate(frame, [8, 52], [0, frac], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const W = vertical ? 860 : 1240;
  return (
    <AbsoluteFill
      style={{
        justifyContent: 'center',
        alignItems: 'center',
        backgroundColor: overImage ? undefined : BG,
      }}
    >
      <div style={{width: W, maxWidth: '88%'}}>
        <Cut start={0}>
          <Kicker size={vertical ? 30 : 28}>
            {spec.label ?? 'TIMELINE'}
          </Kicker>
        </Cut>
        <Cut start={4}>
          <div
            style={{
              fontFamily: HEAVY,
              fontWeight: 800,
              fontSize: vertical ? 150 : 170,
              color: INK,
              margin: '10px 0 26px',
              letterSpacing: 2,
            }}
          >
            {spec.targetYear}
          </div>
        </Cut>
        <Cut start={8}>
          <div style={{position: 'relative', height: 10, background: '#2a2a2e'}}>
            <div
              style={{
                position: 'absolute',
                left: 0,
                top: 0,
                bottom: 0,
                width: `${sweep * 100}%`,
                background: BAR_RED,
              }}
            />
            <div
              style={{
                position: 'absolute',
                left: `calc(${sweep * 100}% - 3px)`,
                top: -14,
                width: 6,
                height: 38,
                background: INK,
              }}
            />
          </div>
        </Cut>
        <Cut start={8}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              marginTop: 16,
              fontFamily: MONO,
              fontSize: vertical ? 30 : 28,
              color: MUTED,
            }}
          >
            <span>{spec.startYear}</span>
            <span>{spec.endYear}</span>
          </div>
        </Cut>
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// MapCallout: full-bleed satellite map (scripts/fetch_map.py via Mapbox),
// red pin drops with a spring onto the location, pulse ring, label card
// hard-cuts in beside it. Shutter click fires as the pin lands — the
// reference video's signature move on its person/location intros.
// ---------------------------------------------------------------------------
const MapCalloutOverlay: React.FC<{
  spec: Extract<OverlaySpec, {type: 'map-callout'}>;
}> = ({spec}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const vertical = height > width;
  const cx = width / 2;
  const cy = height / 2;
  // pin drops from above and settles with a spring
  const drop = spring({frame: frame - 6, fps, config: {damping: 14, stiffness: 160}});
  const pinY = interpolate(drop, [0, 1], [-height * 0.45, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  // pulse ring expanding from the pin, looping
  const pulse = (frame - 24) % 48;
  const ringR = interpolate(pulse, [0, 48], [10, vertical ? 190 : 150], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const ringO = interpolate(pulse, [0, 48], [0.85, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const pinSize = vertical ? 92 : 84;
  return (
    <AbsoluteFill style={{backgroundColor: BG}}>
      <Img
        src={staticFile(spec.mapImage)}
        style={{width: '100%', height: '100%', objectFit: 'cover'}}
      />
      {/* dim just enough for the label to read */}
      <AbsoluteFill
        style={{
          background:
            'linear-gradient(to top, rgba(0,0,0,0.55) 0%, transparent 32%)',
        }}
      />
      {frame >= 24 && (
        <div
          style={{
            position: 'absolute',
            left: cx - ringR,
            top: cy - ringR,
            width: ringR * 2,
            height: ringR * 2,
            borderRadius: '50%',
            border: '5px solid rgba(255,70,50,0.9)',
            opacity: ringO,
          }}
        />
      )}
      {/* pin: teardrop built from a circle + rotated square */}
      <div
        style={{
          position: 'absolute',
          left: cx - pinSize / 2,
          top: cy - pinSize * 1.35 + pinY,
          width: pinSize,
          height: pinSize * 1.35,
        }}
      >
        <div
          style={{
            width: pinSize,
            height: pinSize,
            borderRadius: '50%',
            background: '#e23a2e',
            border: `${Math.max(6, pinSize * 0.09)}px solid white`,
            boxShadow: '0 10px 30px rgba(0,0,0,0.5)',
          }}
        />
        <div
          style={{
            position: 'absolute',
            left: pinSize * 0.28,
            top: pinSize * 0.72,
            width: pinSize * 0.44,
            height: pinSize * 0.44,
            background: '#e23a2e',
            transform: 'rotate(45deg)',
          }}
        />
      </div>
      {/* shutter click as the pin lands (~frame 24) */}
      <Sequence from={22} name="map-pin-shutter">
        <Audio src={staticFile('sfx/shutter.wav')} volume={0.5} />
      </Sequence>
      <Cut start={30}>
        <div
          style={{
            position: 'absolute',
            left: vertical ? '6%' : '5%',
            bottom: vertical ? '9%' : '8%',
            background: 'rgba(5,5,7,0.88)',
            borderLeft: `10px solid ${BAR_RED}`,
            padding: vertical ? '30px 38px' : '26px 34px',
            maxWidth: vertical ? '84%' : '60%',
          }}
        >
          <div
            style={{
              fontFamily: MONO,
              fontSize: vertical ? 30 : 26,
              letterSpacing: 6,
              color: MUTED,
              textTransform: 'uppercase',
              marginBottom: 10,
            }}
          >
            {spec.location}
          </div>
          <div
            style={{
              fontFamily: HEAVY,
              fontWeight: 800,
              fontSize: vertical ? 62 : 56,
              color: INK,
              lineHeight: 1.15,
            }}
          >
            {spec.label}
          </div>
          {spec.note && (
            <div
              style={{
                fontFamily: SERIF,
                fontSize: vertical ? 32 : 28,
                color: MUTED,
                marginTop: 10,
              }}
            >
              {spec.note}
            </div>
          )}
        </div>
      </Cut>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// Question: a giant hook question ("Why risk an entire armored force?"),
// lines hard-cutting in staggered. The reference video's engagement beat.
// ---------------------------------------------------------------------------
const QuestionOverlay: React.FC<{
  spec: Extract<OverlaySpec, {type: 'question'}>;
  overImage?: boolean;
}> = ({spec, overImage}) => {
  const vertical = useVertical();
  // simple word-wrap into lines of ~6 words for the stagger
  const words = spec.text.split(/\s+/);
  const lines: string[] = [];
  let cur = '';
  words.forEach((w) => {
    const next = cur ? cur + ' ' + w : w;
    if (next.split(' ').length > 6 && cur) {
      lines.push(cur);
      cur = w;
    } else {
      cur = next;
    }
  });
  if (cur) lines.push(cur);
  return (
    <AbsoluteFill
      style={{
        justifyContent: 'center',
        alignItems: 'center',
        backgroundColor: overImage ? undefined : BG,
        padding: '0 8%',
      }}
    >
      <div style={{textAlign: 'center', maxWidth: vertical ? '92%' : '80%'}}>
        {lines.map((line, i) => (
          <Cut key={i} start={i * 9}>
            <div
              style={{
                fontFamily: SERIF,
                fontWeight: 700,
                fontSize: vertical ? 72 : 76,
                color: INK,
                lineHeight: 1.25,
              }}
            >
              {line}
              {i === lines.length - 1 && (
                <span style={{color: BAR_RED}}>?</span>
              )}
            </div>
          </Cut>
        ))}
        {spec.sub && (
          <Cut start={lines.length * 9}>
            <div
              style={{
                fontFamily: MONO,
                fontSize: vertical ? 30 : 28,
                letterSpacing: 5,
                color: MUTED,
                marginTop: 28,
                textTransform: 'uppercase',
              }}
            >
              {spec.sub}
            </div>
          </Cut>
        )}
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// BoldWord: one enormous word/phrase ("Every Man", "Failed"), hard cut
// with the standard card pop (scale 1.06→1 over 8 frames).
// ---------------------------------------------------------------------------
const BoldWordOverlay: React.FC<{
  spec: Extract<OverlaySpec, {type: 'bold-word'}>;
  overImage?: boolean;
}> = ({spec, overImage}) => {
  const frame = useCurrentFrame();
  const vertical = useVertical();
  const pop = interpolate(frame, [0, 8], [1.06, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const opacity = interpolate(frame, [0, 8], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  return (
    <AbsoluteFill
      style={{
        justifyContent: 'center',
        alignItems: 'center',
        backgroundColor: overImage ? undefined : BG,
        padding: '0 6%',
        opacity,
      }}
    >
      <div
        style={{
          transform: `scale(${pop})`,
          textAlign: 'center',
        }}
      >
        <div
          style={{
            fontFamily: HEAVY,
            fontWeight: 900,
            fontSize: vertical ? 150 : 190,
            color: INK,
            textTransform: 'uppercase',
            letterSpacing: 4,
            lineHeight: 1.05,
          }}
        >
          {spec.word}
        </div>
        {spec.sub && (
          <div
            style={{
              fontFamily: MONO,
              fontSize: vertical ? 32 : 30,
              letterSpacing: 6,
              color: BAR_RED,
              marginTop: 24,
              textTransform: 'uppercase',
            }}
          >
            {spec.sub}
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// Checklist: title + rows staggering in top to bottom, red square marker
// per row, label left / value right. For casualty counts, force lists,
// "what it cost" beats — the reference's "Task Force Baum Casualties" card.
// ---------------------------------------------------------------------------
const ChecklistOverlay: React.FC<{
  spec: Extract<OverlaySpec, {type: 'checklist'}>;
  overImage?: boolean;
}> = ({spec, overImage}) => {
  const vertical = useVertical();
  return (
    <AbsoluteFill
      style={{
        justifyContent: 'center',
        alignItems: 'center',
        backgroundColor: overImage ? undefined : BG,
      }}
    >
      <div style={{width: vertical ? 860 : 1080, maxWidth: '88%'}}>
        <Cut start={0}>
          <Kicker size={vertical ? 32 : 30}>{spec.title}</Kicker>
        </Cut>
        <div style={{marginTop: 30}}>
          {spec.items.map((item, i) => (
            <Cut key={i} start={8 + i * 9}>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'baseline',
                  padding: '20px 0',
                  borderBottom: '2px solid #26262b',
                }}
              >
                <div
                  style={{
                    width: vertical ? 30 : 26,
                    height: vertical ? 30 : 26,
                    background: BAR_RED,
                    marginRight: 26,
                    flexShrink: 0,
                    transform: 'translateY(4px)',
                  }}
                />
                <div
                  style={{
                    fontFamily: HEAVY,
                    fontSize: vertical ? 52 : 48,
                    color: INK,
                    flex: 1,
                  }}
                >
                  {item.label}
                </div>
                <div
                  style={{
                    fontFamily: MONO,
                    fontSize: vertical ? 46 : 42,
                    color: INK,
                    fontWeight: 700,
                  }}
                >
                  {item.value}
                </div>
              </div>
            </Cut>
          ))}
        </div>
        {spec.note && (
          <Cut start={8 + spec.items.length * 9}>
            <div
              style={{
                fontFamily: SERIF,
                fontSize: vertical ? 32 : 28,
                color: MUTED,
                marginTop: 26,
              }}
            >
              {spec.note}
            </div>
          </Cut>
        )}
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// WikiQuote: a Wikipedia article screenshot (scripts/wiki_shot.py) with the
// key phrase highlighted, framed like a source document. The screenshot is
// real article text fetched live from the Wikipedia API — never generated.
// The card pops in with the standard overlay timing (handled by the
// renderer); the shot fades in quickly once the card is up.
// ---------------------------------------------------------------------------
const WikiQuoteOverlay: React.FC<{
  spec: Extract<OverlaySpec, {type: 'wiki-quote'}>;
  overImage?: boolean; // ignored: the screenshot is the card's background
}> = ({spec}) => {
  const frame = useCurrentFrame();
  const vertical = useVertical();
  const shotO = interpolate(frame, [6, 14], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  return (
    <AbsoluteFill
      style={{
        backgroundColor: BG,
        justifyContent: 'center',
        alignItems: 'center',
        padding: vertical ? 60 : 90,
      }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: vertical ? '94%' : 1240,
          textAlign: 'center',
        }}
      >
        <Cut>
          <Kicker size={vertical ? 32 : 30}>Wikipedia</Kicker>
        </Cut>
        <Cut start={6}>
          <div
            style={{
              marginTop: 30,
              border: '2px solid rgba(255,255,255,0.35)',
              padding: 12,
              backgroundColor: '#101013',
              boxShadow: '0 24px 70px rgba(0,0,0,0.6)',
              opacity: shotO,
              visibility: frame >= 6 ? 'visible' : 'hidden',
            }}
          >
            <Img
              src={staticFile(spec.image)}
              style={{width: '100%', display: 'block'}}
            />
          </div>
        </Cut>
      </div>
    </AbsoluteFill>
  );
};

export const OverlayRenderer: React.FC<{
  spec: OverlaySpec;
  durationInFrames: number;
  overImage?: boolean; // true: no near-black plate; card floats over a dimmed photo
}> = ({spec, durationInFrames, overImage}) => {
  switch (spec.type) {
    case 'stat':
      return <StatOverlay spec={spec} durationInFrames={durationInFrames} overImage={overImage} />;
    case 'date':
      return <DateOverlay spec={spec} overImage={overImage} />;
    case 'timeline':
      return <TimelineOverlay spec={spec} durationInFrames={durationInFrames} overImage={overImage} />;
    case 'bars':
      return <BarsOverlay spec={spec} overImage={overImage} />;
    case 'table':
      return <TableOverlay spec={spec} durationInFrames={durationInFrames} overImage={overImage} />;
    case 'portrait':
      return <PortraitCardOverlay spec={spec} overImage={overImage} />;
    case 'split':
      return <SplitOverlay spec={spec} overImage={overImage} />;
    case 'quote':
      return <QuoteOverlay spec={spec} overImage={overImage} />;
    case 'list':
      return <ListOverlay spec={spec} overImage={overImage} />;
    case 'diagram':
      return <DiagramOverlay spec={spec} durationInFrames={durationInFrames} overImage={overImage} />;
    case 'year-axis':
      return <YearAxisOverlay spec={spec} overImage={overImage} />;
    case 'map-callout':
      return <MapCalloutOverlay spec={spec} />;
    case 'question':
      return <QuestionOverlay spec={spec} overImage={overImage} />;
    case 'bold-word':
      return <BoldWordOverlay spec={spec} overImage={overImage} />;
    case 'checklist':
      return <ChecklistOverlay spec={spec} overImage={overImage} />;
    case 'wiki-quote':
      return <WikiQuoteOverlay spec={spec} overImage={overImage} />;
  }
};

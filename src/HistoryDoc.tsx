import React from 'react';
import {OverlayRenderer, OverlaySpec} from './overlays';
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
  Video,
} from 'remotion';
// SFX: whoosh + page-turn are from @remotion/sfx (MIT), vendored into
// public/sfx/ at build time by render.py so renders never depend on remote
// fetches. The rest are synthesized locally by scripts/gen_sfx.py (zero
// licensing, filtered-noise synthesis):
//   whoosh      -> sfx/whoosh.wav       (scene transitions)
//   shutter     -> sfx/shutter.wav      (portrait reveals, map pin drops)
//   click       -> sfx/click.wav        (select scene transitions)
//   page-turn   -> sfx/page-turn.wav    (map/document scenes)
//   boom        -> sfx/boom.wav         (dramatic beats)
//   riser       -> sfx/riser.wav        (pre-reveal tension swell)
//   stinger     -> sfx/stinger.wav      (overlay card pops, stat reveals)

export type PortraitEvent = {
  file: string; // path under public/, e.g. "images/portrait_01_0.jpg"
  name: string; // display name, e.g. "Isoroku Yamamoto"
  startFrame: number; // relative to the segment's start
  endFrame: number;
  naturalW?: number; // source image size — card fits the photo as-is,
  naturalH?: number; // never cropped or enlarged beyond these bounds
};

export type DocSegment = {
  text: string;
  imageFile: string; // path under public/, e.g. "images/seg_00.jpg"
  clipFile?: string | null; // real video clip, e.g. "clips/clip_00.mp4"
  clipFrames?: number; // the clip's own length in frames (drives looping)
  clipNaturalW?: number; // source clip size — shown exactly as it is,
  clipNaturalH?: number; // centered, scaled down only, never upscaled
  audioFile: string; // path under public/, e.g. "audio/seg_00.mp3"
  durationInFrames: number;
  wordTimings?: [number, number][] | null; // per-word [start,end] seconds
  // from faster-whisper (render.py word-clock); captions time phrases on
  // the real voice when present, else fall back to spoken-length estimate
  isMapOrDoc: boolean;
  personName?: string; // legacy: first named person (name now rides with portraits)
  portraits?: PortraitEvent[]; // timed portrait overlays (portraits.py)
  overlay?: OverlaySpec | null; // full-screen graphic card chosen by the overlay director
};

export type HistoryDocProps = {
  segments: DocSegment[];
  gridBg?: string; // looping grid texture behind natural-size clips
  gridFrames?: number; // grid clip length in frames (drives its loop)
};

// ---------------------------------------------------------------------------
// Film grain: a pre-rendered 8-frame noise loop (public/grain/grain-*.png,
// generated once by scripts/gen_grain.mjs) cycled per frame with
// mix-blend-mode: overlay. Best practice: pre-rendered grain is far
// cheaper at render time than computing per-pixel noise every frame,
// and it shimmers like real film because the pattern changes each frame.
// ---------------------------------------------------------------------------
const GRAIN_FRAMES = 8;

const FilmGrain: React.FC = () => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  // portrait renders use the 540x960 grain tiles so the noise scale matches
  const dir = height > width ? 'grain-portrait' : 'grain';
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <Img
        src={staticFile(`${dir}/grain-${frame % GRAIN_FRAMES}.png`)}
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'fill',
          opacity: 0.16,
          mixBlendMode: 'overlay',
        }}
      />
    </AbsoluteFill>
  );
};

// Ken Burns: slow zoom + lateral pan, alternating direction per segment,
// with a short fade-in so cuts land softly (best practice for stills).
// Scene fade-in length (frames). 30 = 1s at 30fps: a deliberate
// cinematic fade up from black at each scene start, not a flicker.
const SCENE_FADE_FRAMES = 60;

const KenBurnsImage: React.FC<{
  src: string;
  durationInFrames: number;
  index: number;
}> = ({src, durationInFrames, index}) => {
  const frame = useCurrentFrame();
  const progress = durationInFrames <= 1 ? 0 : frame / (durationInFrames - 1);
  const zoomIn = index % 2 === 0;
  const scale = interpolate(progress, [0, 1], zoomIn ? [1.05, 1.22] : [1.22, 1.05]);
  const panX = interpolate(progress, [0, 1], zoomIn ? [-30, 30] : [30, -30]);
  const panY = interpolate(progress, [0, 1], [12, -12]);
  // Scene fade-in (Lawal 2026-09-28): a slow 2s cinematic fade up from
  // black for emotional pacing. The 1s version felt too rushed at each cut.
  const fadeIn = interpolate(frame, [0, SCENE_FADE_FRAMES], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  return (
    <AbsoluteFill
      style={{overflow: 'hidden', backgroundColor: 'black', opacity: fadeIn}}
    >
      <Img
        src={staticFile(src)}
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          transform: `scale(${scale}) translate(${panX}px, ${panY}px)`,
        }}
      />
      {/* subtle vignette */}
      <AbsoluteFill
        style={{
          background:
            'radial-gradient(ellipse at center, transparent 55%, rgba(0,0,0,0.55) 100%)',
        }}
      />
    </AbsoluteFill>
  );
};

// Video clip background: real archival footage instead of a still. The
// trimmed clip (~6s) loops to fill the segment via stacked Sequences —
// Remotion's renderer seeks video per frame, so a native `loop` attribute
// would NOT loop in the rendered output; replaying the clip in each
// sub-sequence does. Same fade-in + vignette treatment as KenBurnsImage.
// The clip is silent (audio stripped at trim time); narration, SFX,
// captions, portraits, overlay cards and film grain all play over it
// unchanged.
const ClipBackground: React.FC<{
  src: string;
  durationInFrames: number;
  clipFrames: number;
  naturalW?: number;
  naturalH?: number;
  gridBg?: string;
  gridFrames?: number;
}> = ({
  src,
  durationInFrames,
  clipFrames,
  naturalW,
  naturalH,
  gridBg,
  gridFrames,
}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const fadeIn = interpolate(frame, [0, SCENE_FADE_FRAMES], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const per = Math.max(1, clipFrames);
  const loops = Math.max(1, Math.ceil(durationInFrames / per));
  // Show the clip BIG: 3x its natural size, centered over the grid.
  // (Lawal: the tiny 320x240 reels were too small at 1x.) Still capped
  // to fit the frame — scaled down only if 3x would overflow — and
  // never cropped.
  const natW = naturalW && naturalW > 0 ? naturalW : width;
  const natH = naturalH && naturalH > 0 ? naturalH : height;
  const fit = Math.min(3, width / natW, height / natH);
  const dispW = Math.max(1, Math.round(natW * fit));
  const dispH = Math.max(1, Math.round(natH * fit));
  const gper = Math.max(1, gridFrames ?? 0);
  const gloops = gridBg ? Math.max(1, Math.ceil(durationInFrames / gper)) : 0;
  return (
    <AbsoluteFill
      style={{overflow: 'hidden', backgroundColor: 'black', opacity: fadeIn}}
    >
      {gridBg &&
        Array.from({length: gloops}).map((_, i) => {
          const from = i * gper;
          const dur = Math.min(gper, durationInFrames - from);
          if (dur <= 0) {
            return null;
          }
          return (
            <Sequence key={`g${i}`} from={from} durationInFrames={dur}>
              <Video
                src={staticFile(gridBg)}
                style={{
                  width: '100%',
                  height: '100%',
                  objectFit: 'cover',
                }}
              />
            </Sequence>
          );
        })}
      {Array.from({length: loops}).map((_, i) => {
        const from = i * per;
        const dur = Math.min(per, durationInFrames - from);
        if (dur <= 0) {
          return null;
        }
        return (
          <Sequence key={i} from={from} durationInFrames={dur}>
            <AbsoluteFill
              style={{
                justifyContent: 'center',
                alignItems: 'center',
              }}
            >
              <Video
                src={staticFile(src)}
                style={{
                  width: dispW,
                  height: dispH,
                }}
              />
            </AbsoluteFill>
          </Sequence>
        );
      })}
      {/* subtle vignette */}
      <AbsoluteFill
        style={{
          background:
            'radial-gradient(ellipse at center, transparent 55%, rgba(0,0,0,0.55) 100%)',
        }}
      />
    </AbsoluteFill>
  );
};

// Scene background: the real video clip when the segment has one,
// otherwise the Ken Burns still. Used by both overlay and plain segments.
const SceneBackground: React.FC<{
  segment: DocSegment;
  index: number;
  gridBg?: string;
  gridFrames?: number;
}> = ({segment, index, gridBg, gridFrames}) =>
  segment.clipFile && segment.clipFrames ? (
    <ClipBackground
      src={segment.clipFile}
      durationInFrames={segment.durationInFrames}
      clipFrames={segment.clipFrames}
      naturalW={segment.clipNaturalW}
      naturalH={segment.clipNaturalH}
      gridBg={gridBg}
      gridFrames={gridFrames}
    />
  ) : (
    <KenBurnsImage
      src={segment.imageFile}
      durationInFrames={segment.durationInFrames}
      index={index}
    />
  );

// Split narration into short subtitle phrases (<= ~42 chars) so the
// caption bar shows one punchy line at a time instead of a wall of text.
// Phrases are timed by character fraction (the TTS gives no word
// timestamps — same approach as portrait/overlay cue timing).
const CAPTION_MAX_CHARS = 42;

function splitCaptions(text: string): string[] {
  const chunks = text
    .split(/(?<=[.!?—:;])\s+/)
    .map((s) => s.trim())
    .filter(Boolean);
  const phrases: string[] = [];
  for (const c of chunks) {
    let line = '';
    for (const w of c.split(/\s+/)) {
      const next = line ? line + ' ' + w : w;
      if (next.length > CAPTION_MAX_CHARS && line) {
        phrases.push(line);
        line = w;
      } else {
        line = next;
      }
    }
    if (line) phrases.push(line);
  }
  // merge dangling fragments (e.g. "binoculars —") into the previous phrase
  const merged: string[] = [];
  for (const p of phrases) {
    const last = merged[merged.length - 1];
    if (last && p.length < 15 && last.length + 1 + p.length <= 50) {
      merged[merged.length - 1] = last + ' ' + p;
    } else {
      merged.push(p);
    }
  }
  return merged;
}

// Caption timing model (2026-09-27): TTS gives no word timestamps, so each
// phrase is timed by its SPOKEN length, not its raw character count:
//  1. digits are expanded to the words the narrator actually says
//     ("1944" -> "nineteen forty four") — otherwise number-heavy phrases
//     flip to the next caption while the number is still being spoken;
//  2. terminal punctuation earns pause time (the narrator pauses at
//     commas/periods, and those pauses sit at phrase boundaries);
//  3. render.py trims leading/trailing silence from each segment MP3, so
//     frame 0 of the scene is (nearly) the first spoken word.
const ONES = [
  'zero','one','two','three','four','five','six','seven','eight','nine',
  'ten','eleven','twelve','thirteen','fourteen','fifteen','sixteen',
  'seventeen','eighteen','nineteen',
];
const TENS = [
  '','','twenty','thirty','forty','fifty','sixty','seventy','eighty','ninety',
];

function twoDigitWord(n: number): string {
  if (n < 20) return ONES[n];
  const t = Math.floor(n / 10);
  const o = n % 10;
  return o ? `${TENS[t]} ${ONES[o]}` : TENS[t];
}

function cardinalWord(n: number): string {
  if (n < 100) return twoDigitWord(n);
  if (n < 1000) {
    const h = Math.floor(n / 100);
    const r = n % 100;
    return r ? `${ONES[h]} hundred ${twoDigitWord(r)}` : `${ONES[h]} hundred`;
  }
  const th = Math.floor(n / 1000);
  const r = n % 1000;
  return r ? `${ONES[th]} thousand ${cardinalWord(r)}` : `${ONES[th]} thousand`;
}

// what the narrator says for a digit run, in words (timing use only)
function speakNumber(m: string): string {
  const n = parseInt(m, 10);
  if (n >= 1100 && n <= 2099) {
    const hi = Math.floor(n / 100);
    const lo = n % 100;
    return lo === 0 ? `${twoDigitWord(hi)} hundred` : `${twoDigitWord(hi)} ${twoDigitWord(lo)}`;
  }
  return cardinalWord(n);
}

function expandNumbers(s: string): string {
  return s.replace(/\b\d{1,4}\b/g, speakNumber);
}

// spoken length of a caption phrase, in "character equivalents": expanded
// words plus a pause allowance for the terminal punctuation.
function phraseSpokenLength(phrase: string): number {
  let len = expandNumbers(phrase).length;
  const last = phrase.trim().slice(-1);
  if (last === '.' || last === '!' || last === '?') len += 7;
  else if (last === ',' || last === ';' || last === ':') len += 4;
  else if (last === '—' || last === '-') len += 5;
  return len;
}
const Caption: React.FC<{
  text: string;
  durationInFrames: number;
  wordTimings?: [number, number][] | null;
}> = ({text, durationInFrames, wordTimings}) => {
  const frame = useCurrentFrame();
  const {width, height, fps} = useVideoConfig();
  const vertical = height > width;
  const opacity = interpolate(
    frame,
    [0, 12, durationInFrames - 18, durationInFrames - 1],
    [0, 1, 1, 0],
    {extrapolateRight: 'clamp', extrapolateLeft: 'clamp'}
  );
  const y = interpolate(frame, [0, 14], [24, 0], {
    extrapolateRight: 'clamp',
    extrapolateLeft: 'clamp',
  });
  // which phrase is being spoken now.
  //
  // Word-clock timing (2026-09-28): when render.py measured real word
  // timings with faster-whisper, each caption phrase starts/ends on the
  // actual spoken words — no estimation. The phrases partition the text's
  // words in order, so each phrase maps to an exact word-index span.
  // Falls back to spoken-length estimation when timings are missing or
  // don't line up with the text.
  const phrases = splitCaptions(text);
  const words = text.split(/\s+/).filter(Boolean);
  let phraseBounds: [number, number][] | null = null; // frames
  if (wordTimings && wordTimings.length === words.length) {
    const spans: [number, number][] = [];
    let wi = 0;
    let ok = true;
    for (const p of phrases) {
      const pw = p.split(' ');
      for (let k = 0; k < pw.length; k++) {
        if (words[wi + k] !== pw[k]) {
          ok = false;
          break;
        }
      }
      if (!ok) break;
      spans.push([wi, wi + pw.length - 1]);
      wi += pw.length;
    }
    if (ok && spans.length === phrases.length) {
      phraseBounds = spans.map(([a, b]) => [
        Math.max(0, Math.round(wordTimings[a][0] * fps)),
        Math.min(
          durationInFrames,
          Math.max(1, Math.round(wordTimings[b][1] * fps))
        ),
      ]);
    }
  }
  let idx = phrases.length - 1;
  let phraseStart = 0;
  if (phraseBounds) {
    for (let i = 0; i < phrases.length; i++) {
      if (frame < phraseBounds[i][1]) {
        if (i > 0 && frame < phraseBounds[i][0]) {
          // inside a real speech pause between phrases: hold the previous
          // phrase up instead of flashing the next one early (or blanking)
          idx = i - 1;
          phraseStart = phraseBounds[i - 1][0];
        } else {
          idx = i;
          phraseStart = phraseBounds[i][0];
        }
        break;
      }
    }
  } else {
    // fallback: spoken-length estimation (see phraseSpokenLength above)
    const spokenLens = phrases.map(phraseSpokenLength);
    const totalSpoken = spokenLens.reduce((a, p) => a + p, 0) || 1;
    let acc = 0;
    for (let i = 0; i < phrases.length; i++) {
      const end = ((acc + spokenLens[i]) / totalSpoken) * durationInFrames;
      if (frame < end) {
        idx = i;
        break;
      }
      acc += spokenLens[i];
      phraseStart = end;
    }
  }
  const phraseOpacity = interpolate(frame - phraseStart, [0, 4], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  return (
    <AbsoluteFill
      style={{
        justifyContent: 'flex-end',
        alignItems: 'center',
        paddingBottom: vertical ? 150 : 90,
        opacity,
      }}
    >
      <div
        style={{
          maxWidth: vertical ? '90%' : '82%',
          // classic caption look (Lawal 2026-09-27): yellow type, black
          // outline, no box — readable over any archival photo
          color: '#FFE600',
          fontFamily: 'Georgia, serif',
          fontWeight: 800,
          fontSize: vertical ? 48 : 42,
          lineHeight: 1.45,
          padding: '10px 16px',
          textAlign: 'center',
          transform: `translateY(${y}px)`,
          opacity: phraseOpacity,
          textShadow: [
            '-2px -2px 0 #000',
            '2px -2px 0 #000',
            '-2px 2px 0 #000',
            '2px 2px 0 #000',
            '-2px 0 0 #000',
            '2px 0 0 #000',
            '0 -2px 0 #000',
            '0 2px 0 #000',
            '0 0 8px rgba(0,0,0,0.9)',
          ].join(', '),
        }}
      >
        {phrases[idx] ?? text}
      </div>
    </AbsoluteFill>
  );
};

// Portrait overlay: when the narration names a person, their licensed
// archival portrait slides in as a framed photograph, timed to the mention,
// with the name captioned under the photo. Landscape (16:9): right side.
// Vertical (9:16): centered and larger, rising from below the midline so it
// clears the taller caption bar. Spring entrance (best practice for
// overlays — springs look natural, linear slides look robotic), gentle
// fade-out. The scene image keeps playing behind it.
const PortraitOverlay: React.FC<{event: PortraitEvent}> = ({event}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const vertical = height > width;
  const photoW = vertical ? Math.round(width * 0.58) : 360;
  const photoH = vertical ? Math.round(photoW * 1.25) : 450;
  // Fit the photo inside the frame at its natural aspect ratio — the
  // image is shown exactly as it is, never cropped or enlarged.
  const natW = event.naturalW && event.naturalW > 0 ? event.naturalW : photoW;
  const natH = event.naturalH && event.naturalH > 0 ? event.naturalH : photoH;
  const fit = Math.min(photoW / natW, photoH / natH, 1);
  const dispW = Math.max(1, Math.round(natW * fit));
  const dispH = Math.max(1, Math.round(natH * fit));
  const dur = event.endFrame - event.startFrame;
  const enter = spring({frame, fps, config: {damping: 200, stiffness: 120}});
  const exit = interpolate(frame, [dur - 14, dur - 1], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const x = vertical ? 0 : interpolate(enter, [0, 1], [170, 0]);
  const yIn = vertical ? interpolate(enter, [0, 1], [130, 0]) : 0;
  const opacity = interpolate(enter, [0, 1], [0, 1]) * (1 - exit);
  // landscape: right of center, lifted above the caption bar
  // vertical: centered, upper-middle, clear of the taller caption bar
  const top = vertical
    ? Math.round(height * 0.14)
    : Math.round(height / 2 - 330);
  const side = vertical
    ? {left: Math.round((width - photoW) / 2)}
    : {right: 88};
  return (
    <AbsoluteFill style={{opacity, pointerEvents: 'none'}}>
      <div
        style={{
          position: 'absolute',
          ...side,
          top,
          transform: `translate(${x}px, ${yIn}px)`,
        }}
      >
        <div
          style={{
            backgroundColor: '#efe6d3', // aged photo paper
            padding: '16px 16px 0 16px',
            boxShadow: '0 18px 60px rgba(0,0,0,0.65)',
          }}
        >
          <Img
            src={staticFile(event.file)}
            style={{
              width: dispW,
              height: dispH,
              display: 'block',
              filter: 'sepia(0.28) contrast(1.04)',
            }}
          />
          <div style={{padding: '14px 4px 16px 4px'}}>
            <div
              style={{
                color: '#1c1a16',
                fontFamily: 'Georgia, serif',
                fontSize: vertical ? 38 : 32,
                letterSpacing: 0.5,
                lineHeight: 1.15,
              }}
            >
              {event.name}
            </div>
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

// Overlay card: pops in with a quick scale+fade ~0.4s after the scene
// starts, holds for at most 2.5s, then fades/scales out. The card is
// punctuation, not wallpaper — it never lingers for the whole segment.
// The scene photo dims while the card is up and brightens back after;
// the narration keeps playing underneath throughout.
const OVERLAY_LEAD_FRAMES = 12; // let the scene land before the card pops in
const OVERLAY_MAX_FRAMES = 120; // 4.0s @30fps — cards hold long enough to read
const OVERLAY_MIN_FRAMES = 60; // 2.0s — minimum readable window, even for late cues
const OVERLAY_EARLY_SHIFT = 30; // at most 1s early when a late cue needs room
const OVERLAY_FX_FRAMES = 8; // pop-in / vanish effect length

const OverlayCard: React.FC<{
  spec: OverlaySpec;
  durationInFrames: number; // the card's own window (<= OVERLAY_MAX_FRAMES)
  makeRoom?: boolean; // a portrait shares this card's window — keep the card clear of it
  segment: DocSegment;
  index: number;
  gridBg?: string;
  gridFrames?: number;
}> = ({spec, durationInFrames, makeRoom, segment, index, gridBg, gridFrames}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const vertical = height > width;
  const enter = interpolate(frame, [0, OVERLAY_FX_FRAMES], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const exit = interpolate(
    frame,
    [durationInFrames - OVERLAY_FX_FRAMES, durationInFrames - 1],
    [0, 1],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}
  );
  const live = enter * (1 - exit);
  const scale =
    interpolate(enter, [0, 1], [1.06, 1]) * interpolate(exit, [0, 1], [1, 0.97]);
  // 'blur' bgEffect (Frontier 5.1 style): a blurred copy of the scene's own
  // footage fades in behind the card instead of just dimming the photo.
  // Slightly scaled up so the blur doesn't show transparent edges.
  const blurBg = spec.bgEffect === 'blur';
  return (
    <AbsoluteFill style={{opacity: live, pointerEvents: 'none'}}>
      {blurBg && (
        <AbsoluteFill>
          <div
            style={{
              width: '100%',
              height: '100%',
              transform: 'scale(1.06)',
              filter: 'blur(22px) brightness(0.8)',
            }}
          >
            <SceneBackground
              segment={segment}
              index={index}
              gridBg={gridBg}
              gridFrames={gridFrames}
            />
          </div>
        </AbsoluteFill>
      )}
      {/* dim the scene photo while the card is up */}
      <AbsoluteFill
        style={{backgroundColor: 'black', opacity: (blurBg ? 0.35 : 0.62) * live}}
      />
      <AbsoluteFill
        style={{
          transform: `scale(${scale})`,
          // landscape portraits sit on the right (~480px incl. frame) —
          // narrow the card's lane so wide text wraps instead of sliding
          // underneath the photo (NB: AbsoluteFill sets width:100%, which
          // overrides `right` in LTR — so width must go auto too)
          right: makeRoom && !vertical ? 520 : 0,
          ...(makeRoom && !vertical ? {width: 'auto'} : null),
        }}
      >
        <OverlayRenderer
          spec={spec}
          durationInFrames={durationInFrames}
          overImage
        />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// The card pops in as its cue phrase is spoken: find the cue in the
// segment's narration text, convert the character offset to a time
// fraction (the same approximation portrait timing uses), and start
// the card a beat before the words land — so the card matches the
// speech instead of just decorating the segment. Falls back to the
// 0.4s lead when no cue is given or found.
const CUE_ANTICIPATION_FRAMES = 6;
const cueStartFrame = (
  text: string,
  cue: string | undefined,
  durationInFrames: number
): number => {
  if (cue && text) {
    const idx = text.toLowerCase().indexOf(cue.toLowerCase().trim());
    if (idx >= 0) {
      const frac = idx / text.length;
      return Math.max(
        0,
        Math.round(frac * durationInFrames) - CUE_ANTICIPATION_FRAMES
      );
    }
  }
  return Math.min(
    OVERLAY_LEAD_FRAMES,
    Math.max(0, durationInFrames - 40)
  );
};

const SegmentScene: React.FC<{
  segment: DocSegment;
  index: number;
  startFrame: number;
  gridBg?: string;
  gridFrames?: number;
}> = ({segment, index, startFrame, gridBg, gridFrames}) => {
  // Overlay segments: the segment's archival photo plays as usual; the
  // graphic card pops in briefly over it (dimmed) with an appear/vanish
  // effect, then the scene continues. Narration + transition SFX play;
  // no caption bar (the card carries the text while it's up).
  if (segment.overlay) {
    // The card pops at its cue, but it must stay readable: guarantee a
    // 2-3s window. If the cue is too late in the segment for the full
    // window, shift the card earlier (at most 1s, never before the
    // lead-in) rather than flashing a sub-second card.
    let cardStart = cueStartFrame(
      segment.text,
      segment.overlay.cue,
      segment.durationInFrames
    );
    const latestFullStart = Math.max(
      OVERLAY_LEAD_FRAMES,
      segment.durationInFrames - OVERLAY_MAX_FRAMES - 4
    );
    if (cardStart > latestFullStart) {
      cardStart = Math.max(latestFullStart, cardStart - OVERLAY_EARLY_SHIFT);
    }
    const cardDur = Math.min(
      OVERLAY_MAX_FRAMES,
      Math.max(
        OVERLAY_MIN_FRAMES,
        segment.durationInFrames - cardStart - 4
      )
    );
    // If a portrait is up while the card is, keep the card's text clear
    // of the photo (landscape: right side). No overlap in time → no shift.
    const cardSharesPortrait = (segment.portraits ?? []).some(
      (p) => p.startFrame < cardStart + cardDur && p.endFrame > cardStart
    );
    return (
      <Sequence
        from={startFrame}
        durationInFrames={segment.durationInFrames}
        name={`seg-${index}`}
      >
        <SceneBackground segment={segment} index={index} gridBg={gridBg} gridFrames={gridFrames} />
        <Sequence
          from={cardStart}
          durationInFrames={cardDur}
          name={`overlay-${index}`}
        >
          <OverlayCard
            spec={segment.overlay}
            durationInFrames={cardDur}
            makeRoom={cardSharesPortrait}
            segment={segment}
            index={index}
            gridBg={gridBg}
            gridFrames={gridFrames}
          />
        </Sequence>
        <Audio src={staticFile(segment.audioFile)} />
        <Audio src={staticFile('sfx/whoosh.wav')} volume={0.35} startFrom={4} />
        {/* named people still appear on overlay segments — the card is
            centered, portraits sit on the right, timed to the mention */}
        {(segment.portraits ?? []).map((p, i) => (
          <Sequence
            key={i}
            from={p.startFrame}
            durationInFrames={Math.max(1, p.endFrame - p.startFrame)}
            name={`portrait-${index}-${i}`}
          >
            <PortraitOverlay event={p} />
            <Audio src={staticFile('sfx/shutter.wav')} volume={0.45} />
          </Sequence>
        ))}
      </Sequence>
    );
  }
  return (
    <Sequence
      from={startFrame}
      durationInFrames={segment.durationInFrames}
      name={`seg-${index}`}
    >
      <SceneBackground segment={segment} index={index} gridBg={gridBg} gridFrames={gridFrames} />
      <Caption text={segment.text} durationInFrames={segment.durationInFrames} wordTimings={segment.wordTimings} />
      {/* narration */}
      <Audio src={staticFile(segment.audioFile)} />
      {/* paper/map reveal gets a page turn, otherwise a whoosh into the scene */}
      {segment.isMapOrDoc ? (
        <Audio src={staticFile('sfx/page-turn.wav')} volume={0.45} startFrom={8} />
      ) : (
        <Audio src={staticFile('sfx/whoosh.wav')} volume={0.35} startFrom={4} />
      )}
      {/* named people: portrait photo appears exactly when mentioned,
          with a vintage shutter click — a genuine archival-photo reveal */}
      {(segment.portraits ?? []).map((p, i) => (
        <Sequence
          key={i}
          from={p.startFrame}
          durationInFrames={Math.max(1, p.endFrame - p.startFrame)}
          name={`portrait-${index}-${i}`}
        >
          <PortraitOverlay event={p} />
          <Audio src={staticFile('sfx/shutter.wav')} volume={0.45} />
        </Sequence>
      ))}
    </Sequence>
  );
};

// Scene transitions (2026-09-27): film burn stays the anchor, rotating
// with fast-flash, light-leak, and glitch by scene index. Deterministic
// (no randomness) so renders are reproducible. Lawal's reference video
// leans on flash cuts between scenes; the burn keeps our cinematic base.
const BURN_DURATION = 24; // frames straddling the cut (0.8s at 30fps)
const BURN_CLIPS = 3;

const TRANSITION_ORDER = [
  'burn',
  'flash',
  'burn',
  'leak',
  'burn',
  'glitch',
] as const;
type TransitionKind = (typeof TRANSITION_ORDER)[number];
const TRANSITION_FRAMES: Record<TransitionKind, number> = {
  burn: 24,
  flash: 12,
  leak: 24,
  glitch: 14,
};
const transitionKind = (index: number): TransitionKind =>
  TRANSITION_ORDER[index % TRANSITION_ORDER.length];

// Fast flash: white frame flashing over the cut (0.4s). The reference
// video's most-used transition.
const FastFlash: React.FC = () => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 6, 12], [0, 1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  return <AbsoluteFill style={{backgroundColor: 'white', opacity}} />;
};

// Light leak: warm gradient washing across the frame with screen blend,
// alternating sweep direction by scene index.
const LightLeak: React.FC<{index: number}> = ({index}) => {
  const frame = useCurrentFrame();
  const dur = TRANSITION_FRAMES.leak;
  const opacity = interpolate(frame, [0, dur / 2, dur], [0, 0.9, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const x = interpolate(frame, [0, dur], [-45, 45], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const dir = index % 2 === 0 ? 1 : -1;
  return (
    <AbsoluteFill style={{mixBlendMode: 'screen', opacity}}>
      <div
        style={{
          position: 'absolute',
          inset: '-20%',
          background:
            'linear-gradient(105deg, transparent 20%, rgba(255,120,40,0.55) 42%, rgba(255,220,150,0.85) 50%, rgba(255,80,30,0.5) 58%, transparent 80%)',
          transform: `translateX(${dir * x}%)`,
        }}
      />
    </AbsoluteFill>
  );
};

// Glitch: seeded slice-displacement bars + chromatic flicker over the cut.
// Seeded by scene index — same index, same glitch, every render.
const Glitch: React.FC<{index: number}> = ({index}) => {
  const frame = useCurrentFrame();
  const dur = TRANSITION_FRAMES.glitch;
  if (frame >= dur) return null;
  const rnd = (n: number) => {
    const x = Math.sin(index * 127.1 + n * 311.7) * 43758.5453;
    return x - Math.floor(x);
  };
  const on = Math.floor(frame / 2) % 2 === 0;
  return (
    <AbsoluteFill style={{opacity: on ? 1 : 0.25}}>
      {[0, 1, 2, 3, 4].map((i) => (
        <div
          key={i}
          style={{
            position: 'absolute',
            top: `${rnd(i) * 85}%`,
            left: '-5%',
            width: '110%',
            height: `${4 + rnd(i + 9) * 8}%`,
            background:
              i % 2 === 0 ? 'rgba(255,0,60,0.28)' : 'rgba(0,220,255,0.28)',
            mixBlendMode: 'screen',
            transform: `translateX(${(rnd(i + 20) - 0.5) * 60}px)`,
          }}
        />
      ))}
      <div
        style={{
          position: 'absolute',
          top: `${rnd(99) * 90}%`,
          left: 0,
          width: '100%',
          height: 3,
          background: 'rgba(255,255,255,0.7)',
        }}
      />
    </AbsoluteFill>
  );
};

const SceneTransition: React.FC<{index: number}> = ({index}) => {
  const kind = transitionKind(index);
  if (kind === 'flash') return <FastFlash />;
  if (kind === 'leak') return <LightLeak index={index} />;
  if (kind === 'glitch') return <Glitch index={index} />;
  return <FilmBurn index={index} />;
};

const FilmBurn: React.FC<{index: number}> = ({index}) => {
  const frame = useCurrentFrame();
  // Opacity ramps up into the cut and back out. The clip is 36 frames;
  // start 6 frames in so its hottest part lands near the cut.
  const opacity = interpolate(
    frame,
    [0, BURN_DURATION / 2, BURN_DURATION],
    [0, 1, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}
  );
  const clip = `transitions/film-burn-${(index % BURN_CLIPS) + 1}.mp4`;
  return (
    <AbsoluteFill style={{mixBlendMode: 'screen', opacity}}>
      <Video
        src={staticFile(clip)}
        startFrom={6}
        style={{width: '100%', height: '100%', objectFit: 'cover'}}
      />
    </AbsoluteFill>
  );
};

export const HistoryDoc: React.FC<HistoryDocProps> = ({
  segments,
  gridBg,
  gridFrames,
}) => {
  let cursor = 0;
  const withStarts = segments.map((s, i) => {
    const startFrame = cursor;
    cursor += s.durationInFrames;
    return {...s, startFrame, index: i};
  });
  return (
    <AbsoluteFill style={{backgroundColor: 'black'}}>
      {withStarts.map((s) => (
        <SegmentScene
          key={s.index}
          segment={s}
          index={s.index}
          startFrame={s.startFrame}
          gridBg={gridBg}
          gridFrames={gridFrames}
        />
      ))}
      {/* scene transitions: rotating burn/flash/leak/glitch over each
          boundary, with a click on every third cut (like the reference —
          sometimes, not every time) landing exactly on the cut */}
      {withStarts.slice(1).map((s) => {
        const kind = transitionKind(s.index);
        const dur = TRANSITION_FRAMES[kind];
        return (
          <Sequence
            key={`tr-${s.index}`}
            from={Math.max(0, s.startFrame - dur / 2)}
            durationInFrames={dur}
            name={`tr-${s.index}`}
          >
            <SceneTransition index={s.index} />
            {s.index % 3 === 0 && (
              <Sequence from={Math.floor(dur / 2)} name={`click-${s.index}`}>
                <Audio src={staticFile('sfx/click.wav')} volume={0.5} />
              </Sequence>
            )}
          </Sequence>
        );
      })}
      {/* film grain over the whole composition */}
      <FilmGrain />
    </AbsoluteFill>
  );
};

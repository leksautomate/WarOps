import React from 'react';
import {Composition, CalculateMetadataFunction} from 'remotion';
import {z} from 'zod';
import {HistoryDoc} from './HistoryDoc';

// render.py adds width/height to the props (orientation rule: short scripts
// go 9:16 vertical, longer ones 16:9). calculateMetadata applies them so the
// composition, useVideoConfig(), and every layout component follow.
const rootSchema = z.object({
  segments: z.array(
    z.object({
      text: z.string(),
      imageFile: z.string(),
      clipFile: z.string().nullable().optional(),
      clipFrames: z.number().optional(),
      audioFile: z.string(),
      durationInFrames: z.number(),
      wordTimings: z
        .array(z.tuple([z.number(), z.number()]))
        .nullable()
        .optional(),
      isMapOrDoc: z.boolean(),
      personName: z.string().optional(),
      overlay: z.any().optional(), // OverlaySpec from src/overlays.tsx
      portraits: z
        .array(
          z.object({
            file: z.string(),
            name: z.string(),
            startFrame: z.number(),
            endFrame: z.number(),
            naturalW: z.number().optional(),
            naturalH: z.number().optional(),
          })
        )
        .optional(),
    })
  ),
  width: z.number().optional(),
  height: z.number().optional(),
  gridBg: z.string().optional(),
  gridFrames: z.number().optional(),
});

type RootProps = z.infer<typeof rootSchema>;

const calculateMetadata: CalculateMetadataFunction<RootProps> = ({props}) => {
  const total = (props.segments ?? []).reduce(
    (acc, s) => acc + s.durationInFrames,
    0
  );
  return {
    durationInFrames: Math.max(total, 1),
    fps: 30,
    width: props.width ?? 1920,
    height: props.height ?? 1080,
  };
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="HistoryDoc"
        schema={rootSchema}
        component={HistoryDoc}
        durationInFrames={30}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{segments: []}}
        calculateMetadata={calculateMetadata}
      />
    </>
  );
};

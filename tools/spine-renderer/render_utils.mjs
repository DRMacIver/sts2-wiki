/**
 * Shared rendering utilities for Spine skeleton renderers.
 *
 * The spine-canvas SkeletonRenderer uses canvas clip() paths for triangle
 * rendering. On skeletons with many mesh attachments, these clip paths
 * accumulate and corrupt the canvas state, causing toBuffer() to OOM or
 * produce blank output. This module provides a slot-by-slot fallback that
 * renders each slot to its own canvas and composites via raw pixel data.
 */
import { createCanvas } from "canvas";
import {
  SkeletonRenderer,
  RegionAttachment,
  MeshAttachment,
} from "@esotericsoftware/spine-canvas";

const BLANK_PNG_THRESHOLD = 2000; // bytes — a blank 512x512 transparent PNG is ~1114 bytes

/**
 * Render a skeleton to a canvas. Returns the raw pixel ImageData at renderSize.
 * First tries normal all-at-once rendering. If the result is blank (clip path
 * corruption), falls back to slot-by-slot compositing.
 */
export function renderSkeleton(skeleton, renderSize, scale, minX, minY, maxX, maxY) {
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;

  // Try normal render first
  const canvas = createCanvas(renderSize, renderSize);
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, renderSize, renderSize);
  ctx.save();
  ctx.translate(renderSize / 2, renderSize / 2);
  ctx.scale(scale, -scale);
  ctx.translate(-cx, -cy);
  const renderer = new SkeletonRenderer(ctx);
  renderer.triangleRendering = true;
  renderer.draw(skeleton);
  ctx.restore();

  // Check pixel count via getImageData (bypasses clip corruption)
  const imgData = ctx.getImageData(0, 0, renderSize, renderSize);
  let nonTransparent = 0;
  for (let i = 3; i < imgData.data.length; i += 4) {
    if (imgData.data[i] > 0) nonTransparent++;
  }

  // Also check if toBuffer would work by trying it
  let bufferOk = false;
  try {
    const testBuf = canvas.toBuffer("image/png");
    bufferOk = testBuf.length > BLANK_PNG_THRESHOLD;
  } catch {
    // OOM — canvas state corrupted
  }

  if (bufferOk && nonTransparent > renderSize * renderSize * 0.01) {
    // Normal render succeeded — copy pixels to fresh canvas to be safe
    return imgData;
  }

  // Fallback: slot-by-slot compositing
  console.log("    (using slot-by-slot fallback renderer)");
  return renderSlotBySlot(skeleton, renderSize, scale, cx, cy);
}

function renderSlotBySlot(skeleton, renderSize, scale, cx, cy) {
  const compPixels = new Uint8ClampedArray(renderSize * renderSize * 4);

  for (const slot of skeleton.drawOrder) {
    const att = slot.getAttachment();
    if (!att) continue;
    if (!(att instanceof RegionAttachment) && !(att instanceof MeshAttachment)) continue;

    // Save and hide all other slots
    const saved = [];
    for (const s of skeleton.drawOrder) {
      if (s !== slot) {
        saved.push({ slot: s, att: s.getAttachment() });
        s.setAttachment(null);
      }
    }

    // Render this single slot
    const tempCanvas = createCanvas(renderSize, renderSize);
    const tempCtx = tempCanvas.getContext("2d");
    tempCtx.save();
    tempCtx.translate(renderSize / 2, renderSize / 2);
    tempCtx.scale(scale, -scale);
    tempCtx.translate(-cx, -cy);
    const renderer = new SkeletonRenderer(tempCtx);
    renderer.triangleRendering = true;
    renderer.draw(skeleton);
    tempCtx.restore();

    // Restore all slots
    for (const { slot: s, att: a } of saved) s.setAttachment(a);

    // Alpha-composite raw pixels (source-over blending)
    const src = tempCtx.getImageData(0, 0, renderSize, renderSize).data;
    for (let i = 0; i < src.length; i += 4) {
      const sa = src[i + 3] / 255;
      if (sa === 0) continue;
      const da = compPixels[i + 3] / 255;
      const outA = sa + da * (1 - sa);
      if (outA === 0) continue;
      compPixels[i]     = (src[i] * sa + compPixels[i] * da * (1 - sa)) / outA;
      compPixels[i + 1] = (src[i + 1] * sa + compPixels[i + 1] * da * (1 - sa)) / outA;
      compPixels[i + 2] = (src[i + 2] * sa + compPixels[i + 2] * da * (1 - sa)) / outA;
      compPixels[i + 3] = outA * 255;
    }
  }

  // Return as ImageData
  const resultCanvas = createCanvas(renderSize, renderSize);
  const resultCtx = resultCanvas.getContext("2d");
  const resultData = resultCtx.createImageData(renderSize, renderSize);
  resultData.data.set(compPixels);
  return resultData;
}

/**
 * Convert ImageData to a downscaled PNG buffer.
 */
export function imageDataToPng(imgData, renderSize, outputSize) {
  const fullCanvas = createCanvas(renderSize, renderSize);
  const fullCtx = fullCanvas.getContext("2d");
  fullCtx.putImageData(imgData, 0, 0);

  if (renderSize === outputSize) {
    return fullCanvas.toBuffer("image/png");
  }

  const outCanvas = createCanvas(outputSize, outputSize);
  const outCtx = outCanvas.getContext("2d");
  outCtx.drawImage(fullCanvas, 0, 0, outputSize, outputSize);
  return outCanvas.toBuffer("image/png");
}

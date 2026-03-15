import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { z } from 'astro/zod';

const cards = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/cards' }),
  schema: z.object({
    title: z.string(),
    class_name: z.string(),
    character: z.string(),
    energy_cost: z.number(),
    type: z.string(),
    rarity: z.string(),
    target: z.string(),
    keywords: z.array(z.string()).default([]),
    vars: z.array(z.object({
      type: z.string(),
      base_value: z.number(),
      upgraded_value: z.number().optional(),
    })).default([]),
    description_plain: z.string().default(''),
    description_html: z.string().default(''),
    upgraded_description_plain: z.string().optional(),
    upgraded_description_html: z.string().optional(),
    upgraded_cost: z.number().optional(),
    referenced_powers: z.array(z.string()).default([]),
    x_cost: z.boolean().default(false),
    pool: z.string().default(''),
  }),
});

export const collections = { cards };

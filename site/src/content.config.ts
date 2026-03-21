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
    referenced_powers: z.array(z.object({
      class_name: z.string(),
      title: z.string(),
      slug: z.string(),
    })).default([]),
    x_cost: z.boolean().default(false),
    star_cost: z.number().optional(),
    x_star_cost: z.boolean().optional(),
    pool: z.string().default(''),
    unlocked_by: z.string().optional(),
    notes: z.string().optional(),
  }),
});

const powers = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/powers' }),
  schema: z.object({
    title: z.string(),
    class_name: z.string(),
    power_type: z.string(),
    stack_type: z.string(),
    description_plain: z.string().default(''),
    description_html: z.string().default(''),
    smart_description: z.string().default(''),
  }),
});

const monsters = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/monsters' }),
  schema: z.object({
    title: z.string(),
    class_name: z.string(),
    min_hp: z.number(),
    max_hp: z.number(),
    is_companion: z.boolean().default(false),
    move_pattern: z.string().default(''),
    moves: z.array(z.object({
      id: z.string(),
      title: z.string().default(''),
      intents: z.array(z.object({
        type: z.string(),
        damage: z.number().optional(),
        hits: z.number().optional(),
        amount: z.number().optional(),
      })).default([]),
      effects: z.array(z.string()).default([]),
    })).default([]),
    powers_on_spawn: z.array(z.string()).default([]),
    encounters: z.array(z.object({
      class_name: z.string(),
      title: z.string(),
      slug: z.string(),
    })).default([]),
    notes: z.string().optional(),
  }),
});

const encounters = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/encounters' }),
  schema: z.object({
    title: z.string(),
    class_name: z.string(),
    room_type: z.string(),
    is_weak: z.boolean().default(false),
    monsters: z.array(z.object({
      class_name: z.string(),
      title: z.string(),
      slug: z.string(),
    })).default([]),
    tags: z.array(z.string()).default([]),
    acts: z.array(z.string()).default([]),
  }),
});

const relics = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/relics' }),
  schema: z.object({
    title: z.string(),
    class_name: z.string(),
    rarity: z.string(),
    pool: z.string().default(''),
    image: z.string().default(''),
    description_plain: z.string().default(''),
    description_html: z.string().default(''),
    flavor: z.string().default(''),
    character: z.string().default(''),
    sources: z.array(z.string()).default([]),
  }),
});

const ancients = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/ancients' }),
  schema: z.object({
    title: z.string(),
    class_name: z.string(),
    epithet: z.string().default(''),
    relic_offerings: z.array(z.object({
      title: z.string(),
      description: z.string().default(''),
      slug: z.string(),
      image: z.string().default(''),
    })).default([]),
    acts: z.array(z.string()).default([]),
  }),
});

const potions = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/potions' }),
  schema: z.object({
    title: z.string(),
    class_name: z.string(),
    rarity: z.string(),
    usage: z.string().default('Unknown'),
    target: z.string().default('Unknown'),
    image: z.string().default(''),
    description_plain: z.string().default(''),
    description_html: z.string().default(''),
  }),
});

const events = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/events' }),
  schema: z.object({
    title: z.string(),
    class_name: z.string(),
    description_plain: z.string().default(''),
    description_html: z.string().default(''),
    options: z.array(z.object({
      title: z.string(),
      description: z.string().default(''),
      requires: z.string().optional(),
    })).default([]),
    acts: z.array(z.string()).default([]),
    conditions: z.string().default(''),
    notes: z.string().optional(),
    card_refs: z.array(z.object({
      class_name: z.string(),
      title: z.string(),
      slug: z.string(),
    })).default([]),
    relic_refs: z.array(z.object({
      class_name: z.string(),
      title: z.string(),
      slug: z.string(),
    })).default([]),
  }),
});

const epochs = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/epochs' }),
  schema: z.object({
    title: z.string(),
    class_name: z.string(),
    epoch_id: z.string().default(''),
    era: z.string().default(''),
    era_position: z.number().default(0),
    story: z.string().default(''),
    description: z.string().default(''),
    description_html: z.string().default(''),
    image: z.string().default(''),
    unlocks_cards: z.array(z.union([
      z.string(),
      z.object({ class_name: z.string(), title: z.string(), slug: z.string() }),
    ])).default([]),
    unlocks_relics: z.array(z.union([
      z.string(),
      z.object({ class_name: z.string(), title: z.string(), slug: z.string() }),
    ])).default([]),
    unlocks_events: z.array(z.string()).default([]),
    unlocks_encounters: z.array(z.string()).default([]),
    unlocks_potions: z.array(z.string()).default([]),
    unlocks_ancients: z.array(z.string()).default([]),
  }),
});

const characters = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/characters' }),
  schema: z.object({
    title: z.string(),
    class_name: z.string(),
    description: z.string().default(''),
    aroma: z.string().default(''),
    starting_hp: z.number(),
    starting_gold: z.number(),
    orb_slots: z.number().optional(),
    starting_relic: z.object({
      class_name: z.string(),
      title: z.string(),
      slug: z.string(),
    }),
    starting_deck: z.array(z.object({
      class_name: z.string(),
      title: z.string(),
      slug: z.string(),
    })).default([]),
  }),
});

const ascensions = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/ascensions' }),
  schema: z.object({
    title: z.string(),
    level: z.number(),
    description: z.string().default(''),
    detail: z.string().default(''),
    monster_changes: z.array(z.object({
      monster: z.string(),
      class_name: z.string(),
      property: z.string().optional(),
      base: z.number(),
      ascension: z.number(),
      diff: z.number(),
    })).default([]),
  }),
});

const enchantments = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/enchantments' }),
  schema: z.object({
    title: z.string(),
    class_name: z.string(),
    card_type: z.string().default('Any'),
    description_plain: z.string().default(''),
    description_html: z.string().default(''),
    extra_card_text: z.string().optional(),
    restrictions: z.array(z.string()).default([]),
    stackable: z.boolean().default(false),
  }),
});

export const collections = { cards, powers, monsters, encounters, relics, ancients, events, potions, epochs, characters, ascensions, enchantments };

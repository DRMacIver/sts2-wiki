// @ts-check
import { defineConfig } from 'astro/config';

// https://astro.build/config
export default defineConfig({
  output: 'static',
  site: 'https://drmaciver.github.io',
  base: process.env.ASTRO_BASE || '/sts2-wiki/',
});

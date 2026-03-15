import type { APIRoute } from 'astro';
import { getCollection } from 'astro:content';

export const GET: APIRoute = async () => {
  const base = import.meta.env.BASE_URL;
  const entries: { title: string; url: string; type: string }[] = [];

  const excludedClasses = new Set([
    'DeprecatedPotion', 'DeprecatedEncounter', 'DeprecatedEvent',
    'TheArchitect', 'FakeMerchant',
    'BigDummy', 'MultiAttackMoveMonster', 'OneHpMonster',
    'SingleAttackMoveMonster', 'TenHpMonster', 'TestSubject',
  ]);
  const isExcluded = (item: { data: { class_name: string } }) =>
    excludedClasses.has(item.data.class_name);

  const cards = await getCollection('cards');
  for (const c of cards) {
    entries.push({ title: c.data.title, url: `${base}cards/${c.id}/`, type: 'Card' });
  }

  const relics = await getCollection('relics');
  for (const r of relics) {
    entries.push({ title: r.data.title, url: `${base}relics/${r.id}/`, type: 'Relic' });
  }

  const powers = await getCollection('powers');
  for (const p of powers) {
    entries.push({ title: p.data.title, url: `${base}powers/${p.id}/`, type: 'Effect' });
  }

  const potions = (await getCollection('potions')).filter(p => !isExcluded(p));
  for (const p of potions) {
    entries.push({ title: p.data.title, url: `${base}potions/${p.id}/`, type: 'Potion' });
  }

  const monsters = (await getCollection('monsters')).filter(m => !isExcluded(m));
  for (const m of monsters) {
    entries.push({ title: m.data.title, url: `${base}monsters/${m.id}/`, type: 'Monster' });
  }

  const encounters = (await getCollection('encounters')).filter(e => !isExcluded(e));
  for (const e of encounters) {
    entries.push({ title: e.data.title, url: `${base}encounters/${e.id}/`, type: 'Encounter' });
  }

  const events = (await getCollection('events')).filter(e => !isExcluded(e));
  for (const e of events) {
    entries.push({ title: e.data.title, url: `${base}events/${e.id}/`, type: 'Event' });
  }

  const ancients = await getCollection('ancients');
  for (const a of ancients) {
    entries.push({ title: a.data.title, url: `${base}ancients/${a.id}/`, type: 'Ancient' });
  }

  const epochs = await getCollection('epochs');
  for (const e of epochs) {
    entries.push({ title: e.data.title, url: `${base}epochs/${e.id}/`, type: 'Epoch' });
  }

  entries.sort((a, b) => a.title.localeCompare(b.title));

  return new Response(JSON.stringify(entries), {
    headers: { 'Content-Type': 'application/json' },
  });
};

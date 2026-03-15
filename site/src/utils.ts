/**
 * Clean up stray template artifacts from game localization strings.
 * The game uses a template system like `{var turns}` and `{? conditional|alternative}`.
 * Some of these aren't fully resolved during extraction.
 */
export function cleanDescription(text: string): string {
  if (!text) return '';
  let s = text;

  // FIRST: Convert {TemplateVar} placeholders BEFORE any } stripping
  // These may be inside HTML spans like <span class="desc-gold">{Card1}</span>
  // Need to handle both bare {Var} and HTML-wrapped {Var}
  s = s.replace(/\{([A-Za-z][A-Za-z0-9]*)\}/g, (_, name) => {
    const readable = name
      .replace(/([a-z])([A-Z])/g, '$1 $2')
      .replace(/([A-Z]+)([A-Z][a-z])/g, '$1 $2');
    return `<span class="desc-gold">${readable}</span>`;
  });

  // Handle {Var:plural:singular|plural} syntax
  s = s.replace(/\{(\w+):plural:(\w+)\|(\w+)\}/g, (_, _name, _singular, plural) => {
    return `<span class="desc-gold">${plural}</span>`;
  });

  // Clean ?|hint text} patterns (partially-parsed placeholders)
  s = s.replace(/\?\|[^}]*\}/g, '?');

  // Remove empty conditionals: ?|} or ?\|} (with optional HTML between)
  s = s.replace(/\?\s*\|?\s*\}/g, '');

  // Clean "? word|? words}" plural patterns
  s = s.replace(/\?\s*\w+\s*\|\s*\?\s*\w+\s*\}/g, '?');

  // Clean "? word)" and "? word)|}" patterns
  s = s.replace(/\?\s*(\w+)\s*\)\s*\|?\s*\}/g, '? $1');

  // Clean "word}" where word is preceded by ? (with possible HTML in between)
  // Handle "? turns}", "? cards}", "damage? times}" etc.
  s = s.replace(/(\?\s*(?:<[^>]+>\s*)*)(\w+)\s*\}/g, '$1$2');

  // Clean word} patterns preceded by a space (like "sacrifices}")
  s = s.replace(/\s(\w+)\}/g, ' $1');

  // Strip standalone stray } that aren't part of JS/HTML
  // Only remove } that appear after word characters with no { before
  s = s.replace(/(\w)\}/g, '$1');

  // Convert remaining BBCode tags to readable text
  s = s.replace(/\[star\]/gi, '\u2605');
  s = s.replace(/\[energy\]/gi, '\u26A1');

  // Clean up stray [/color] BBCode closing tags that got through
  s = s.replace(/\[\/\w+\]/g, '');

  // Clean up stray opening BBCode tags that weren't matched
  s = s.replace(/\[\w+[^\]]*\]/g, '');

  // Collapse nested spans where outer span is redundant
  // e.g., <span class="desc-red"><span class="desc-gold">X</span></span> → <span class="desc-gold">X</span>
  s = s.replace(/<span class="desc-\w+">\s*(<span class="desc-\w+">[^<]*<\/span>)\s*<\/span>/g, '$1');

  // Clean up double spaces
  s = s.replace(/  +/g, ' ');

  // Clean up empty parentheses left behind
  s = s.replace(/\(\s*\)/g, '');

  return s.trim();
}

/**
 * Process BBCode tags in text to HTML spans.
 */
export function processBBCode(text: string): string {
  if (!text) return '';
  return text
    .replace(/\[gold\](.*?)\[\/gold\]/gi, '<span class="desc-gold">$1</span>')
    .replace(/\[red\](.*?)\[\/red\]/gi, '<span class="desc-red">$1</span>')
    .replace(/\[green\](.*?)\[\/green\]/gi, '<span class="desc-green">$1</span>')
    .replace(/\[blue\](.*?)\[\/blue\]/gi, '<span class="desc-blue">$1</span>')
    .replace(/\[purple\](.*?)\[\/purple\]/gi, '<span class="desc-purple">$1</span>')
    .replace(/\[orange\](.*?)\[\/orange\]/gi, '<span class="desc-orange">$1</span>')
    .replace(/\[aqua\](.*?)\[\/aqua\]/gi, '<span class="desc-aqua">$1</span>')
    .replace(/\[pink\](.*?)\[\/pink\]/gi, '<span class="desc-pink">$1</span>')
    .replace(/\[rainbow[^\]]*\](.*?)\[\/rainbow\]/gi, '<span class="desc-gold">$1</span>')
    .replace(/\[star\]/gi, '\u2605')
    .replace(/\[energy\]/gi, '\u26A1');
}

/**
 * Get CSS class for character name.
 */
export function charClass(name: string): string {
  const n = name.toLowerCase();
  if (['ironclad', 'silent', 'defect', 'necrobinder', 'regent'].includes(n)) return `char-${n}`;
  return '';
}

// ─── Monster move description generation ───

interface MoveIntent {
  type: string;
  damage?: number;
  hits?: number;
  amount?: number;
}

interface Move {
  id: string;
  title: string;
  intents: MoveIntent[];
  effects: string[];
}

interface MoveDescription {
  /** CSS class for the intent type (intent-attack, intent-block, etc.) */
  intentClass: string;
  /** Short label for the intent tag pill */
  intentLabel: string;
}

/**
 * Generate a consistent description for a single intent.
 */
/**
 * Map monster class name to the image filename (without extension).
 * Many monsters share base skeletons or have different animation names.
 */
const MONSTER_IMAGE_ALIASES: Record<string, string> = {
  TorchHeadAmalgam: 'amalgam',
  GlobeHead: 'orb_head',
  Flyconid: 'flying_mushrooms',
  DecimillipedeSegment: 'decimillipede',
  Doormaker: 'fabricator',
  LivingFog: 'living_smog',
  SkulkingColony: 'living_shield',
  Crusher: 'infested_guardian',
  Ovicopter: 'egg_layer',
  TheAdversaryMkOne: 'infested_prism',
  TheAdversaryMkTwo: 'infested_purifier',
  TheAdversaryMkThree: 'infested_guardian',
  BowlbugEgg: 'bowlbug',
  BowlbugNectar: 'bowlbug',
  BowlbugRock: 'bowlbug',
  BowlbugSilk: 'bowlbug',
  CalcifiedCultist: 'cultists',
  DampCultist: 'cultists',
  BattleFriendV1: 'battleworn_dummy',
  BattleFriendV2: 'battleworn_dummy',
  BattleFriendV3: 'battleworn_dummy',
  BigDummy: 'battleworn_dummy',
};

export function monsterImageName(className: string): string {
  if (MONSTER_IMAGE_ALIASES[className]) return MONSTER_IMAGE_ALIASES[className];
  // Default: convert PascalCase to snake_case
  return className.replace(/([A-Z])/g, (m: string, p1: string, offset: number) =>
    (offset > 0 ? '_' : '') + p1
  ).toLowerCase();
}

/** Map intent type to icon filename */
export function intentIconFile(type: string): string {
  switch (type) {
    case 'attack':
    case 'SingleAttackIntent':
    case 'multi_attack':
    case 'death_blow':
      return 'attack/intent_attack_1.png';
    case 'block':
      return 'intent_defend.png';
    case 'buff':
      return 'intent_buff.png';
    case 'debuff':
      return 'intent_debuff.png';
    case 'stun':
      return 'intent_stun.png';
    case 'sleep':
      return 'intent_sleep.png';
    case 'summon':
      return 'intent_summon.png';
    case 'heal':
      return 'intent_heal.png';
    case 'escape':
      return 'intent_escape.png';
    case 'status':
      return 'intent_status_card.png';
    case 'hidden':
      return 'intent_hidden.png';
    default:
      return 'intent_unknown.png';
  }
}

function describeIntent(intent: MoveIntent): MoveDescription {
  switch (intent.type) {
    case 'attack':
    case 'SingleAttackIntent':
      return {
        intentClass: 'intent-attack',
        intentLabel: intent.damage != null ? String(intent.damage) : 'ATK',
      };
    case 'multi_attack':
      if (intent.damage != null && intent.hits != null) {
        return { intentClass: 'intent-attack', intentLabel: `${intent.damage}x${intent.hits}` };
      } else if (intent.damage != null) {
        return { intentClass: 'intent-attack', intentLabel: `${intent.damage}xN` };
      }
      return { intentClass: 'intent-attack', intentLabel: 'Multi' };
    case 'block':
      return {
        intentClass: 'intent-block',
        intentLabel: intent.amount != null ? `Block ${intent.amount}` : 'Block',
      };
    case 'buff':
      return { intentClass: 'intent-buff', intentLabel: 'Buff' };
    case 'debuff':
      return { intentClass: 'intent-debuff', intentLabel: 'Debuff' };
    case 'stun':
      return { intentClass: 'intent-stun', intentLabel: 'Stun' };
    case 'sleep':
      return { intentClass: 'intent-sleep', intentLabel: 'Sleep' };
    case 'summon':
      return { intentClass: 'intent-summon', intentLabel: 'Summon' };
    case 'heal':
      return { intentClass: 'intent-heal', intentLabel: 'Heal' };
    case 'escape':
      return { intentClass: 'intent-escape', intentLabel: 'Escape' };
    case 'status':
      return { intentClass: 'intent-status', intentLabel: 'Status' };
    case 'hidden':
      return { intentClass: 'intent-escape', intentLabel: '???' };
    case 'death_blow':
      return { intentClass: 'intent-attack', intentLabel: 'Death' };
    default:
      return { intentClass: '', intentLabel: intent.type };
  }
}

/**
 * Build an array of intent tag descriptions for a move.
 */
export function getMoveIntents(move: Move): MoveDescription[] {
  return move.intents.map(describeIntent);
}

/**
 * Build a textual description of what a move does from structured data.
 * Uses effects when available (they have specific buff/debuff names),
 * falls back to intent-derived descriptions when effects is empty.
 */
export function getMoveEffectLines(move: Move, powerSlugs: Record<string, string>, baseUrl: string): string[] {
  const lines: string[] = [];

  if (move.effects.length > 0) {
    // Use effects array — it has specific info like "Apply 2 Frail"
    for (const effect of move.effects) {
      // Skip redundant "N hits" lines — already shown in intent tag
      if (/^\d+ hits?$/i.test(effect)) continue;
      lines.push(linkEffect(effect, powerSlugs, baseUrl));
    }
  } else {
    // Generate from intents when effects is empty
    for (const intent of move.intents) {
      switch (intent.type) {
        case 'attack':
        case 'SingleAttackIntent':
          if (intent.damage != null) {
            lines.push(`Deal <span class="desc-red">${intent.damage}</span> damage`);
          }
          break;
        case 'multi_attack':
          if (intent.damage != null) {
            const hits = intent.hits != null ? ` x${intent.hits}` : '';
            lines.push(`Deal <span class="desc-red">${intent.damage}</span> damage${hits}`);
          }
          break;
        case 'block':
          if (intent.amount != null) {
            lines.push(`Gain <span class="desc-blue">${intent.amount}</span> Block`);
          } else {
            lines.push(`<span class="desc-blue">Block</span>`);
          }
          break;
        case 'buff':
          lines.push(`<span class="desc-gold">Buff</span>`);
          break;
        case 'debuff':
          lines.push(`<span class="desc-purple">Debuff</span>`);
          break;
        case 'heal':
          lines.push(`<span class="desc-green">Heal</span>`);
          break;
        case 'stun':
          lines.push(`<span class="desc-blue">Stun</span>`);
          break;
        case 'sleep':
          lines.push(`<span class="desc-blue">Sleep</span>`);
          break;
        case 'summon':
          lines.push(`<span class="desc-green">Summon</span>`);
          break;
        case 'escape':
          lines.push(`Escape`);
          break;
        case 'status':
          lines.push(`<span class="desc-purple">Apply status</span>`);
          break;
        // hidden, death_blow — no additional description needed
      }
    }
  }

  return lines;
}

/**
 * Convert a single effect string to HTML with linked power names.
 */
function linkEffect(effect: string, powerSlugs: Record<string, string>, baseUrl: string): string {
  // "Apply N PowerName" or "Apply PowerName"
  const applyMatch = effect.match(/^(Apply)\s+(\d+\s+)?(.+)$/);
  if (applyMatch) {
    const amount = applyMatch[2]?.trim();
    const name = applyMatch[3].trim();
    const slug = powerSlugs[name.toLowerCase()];
    const nameHtml = slug
      ? `<a href="${baseUrl}powers/${slug}/">${name}</a>`
      : `<span class="desc-gold">${name}</span>`;
    return amount
      ? `Apply <span class="desc-red">${amount}</span> ${nameHtml}`
      : `Apply ${nameHtml}`;
  }

  // "Gain N Block" or "Gain N PowerName"
  const gainMatch = effect.match(/^(Gain)\s+(\d+)\s+(.+)$/);
  if (gainMatch) {
    const amount = gainMatch[2];
    const name = gainMatch[3].trim();
    if (name === 'Block') {
      return `Gain <span class="desc-blue">${amount}</span> <span class="desc-blue">Block</span>`;
    }
    const slug = powerSlugs[name.toLowerCase()];
    const nameHtml = slug
      ? `<a href="${baseUrl}powers/${slug}/">${name}</a>`
      : `<span class="desc-gold">${name}</span>`;
    return `Gain <span class="desc-green">${amount}</span> ${nameHtml}`;
  }

  // "Deal N damage"
  const dealMatch = effect.match(/^Deal\s+(\d+)\s+damage$/);
  if (dealMatch) {
    return `Deal <span class="desc-red">${dealMatch[1]}</span> damage`;
  }

  // "Heal N"
  const healMatch = effect.match(/^Heal\s+(\d+)$/);
  if (healMatch) {
    return `Heal <span class="desc-green">${healMatch[1]}</span>`;
  }

  // "Add X to discard"
  const addMatch = effect.match(/^Add\s+(.+)\s+to\s+discard$/);
  if (addMatch) {
    return `Add <span class="desc-purple">${addMatch[1]}</span> to discard`;
  }

  // Fallback
  return effect;
}

/**
 * Parse move_pattern text into structured display steps.
 */
export function parsePattern(text: string): string[] {
  if (!text) return [];
  const clean = text.replace(/^"|"$/g, '');

  // Cycle pattern: "Cycles in the order: X -> Y -> Z."
  const cycleMatch = clean.match(/Cycles in the order:\s*(.+)/);
  if (cycleMatch) {
    const moves = cycleMatch[1].split('->').map(m => m.trim().replace(/\.$/, ''));
    return moves.map((m, i) => `${i + 1}. ${m}${i < moves.length - 1 ? ' \u2192' : ' (repeat)'}`);
  }

  // "Starts with X, then cycles: Y -> Z."
  const startCycleMatch = clean.match(/Starts with (.+?),\s*then cycles?:\s*(.+)/);
  if (startCycleMatch) {
    const start = startCycleMatch[1].trim().replace(/\.$/, '');
    const cycleMovesRaw = startCycleMatch[2].split('->').map(m => m.trim().replace(/\.$/, ''));
    const steps = [`1. ${start}`];
    cycleMovesRaw.forEach((m, i) => {
      steps.push(`${i + 2}. ${m}${i < cycleMovesRaw.length - 1 ? ' \u2192' : ' (repeat from 2)'}`);
    });
    return steps;
  }

  // Sequential: split on ". "
  const sentences = clean.split(/\.\s+/).filter(s => s.trim()).map(s => s.replace(/\.$/, '').trim());
  return sentences;
}

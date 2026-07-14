/**
 * Parse RePoE mods.min.json → structured equipment modifier data
 * Source: https://github.com/brather1ng/RePoE
 *
 * Filters: domain=1 (Item), generation_type=1 (Prefix) or 2 (Suffix)
 * Output: POE1 equipment affixes grouped by stat, with tiers
 */

import { readFileSync, writeFileSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const INPUT = join(__dirname, '..', 'repoe_mods.min.json');
const OUTPUT = join(__dirname, '..', '..', 'POE1', 'data', 'equipment-modifiers.json');

console.log('Loading mods.min.json...');
const raw = JSON.parse(readFileSync(INPUT, 'utf-8'));

const results = [];
let total = 0;
let filtered = 0;

for (const [modId, mod] of Object.entries(raw)) {
    total++;
    if (mod.domain !== 'item') continue;
    if (mod.generation_type !== 'prefix' && mod.generation_type !== 'suffix') continue;
    filtered++;

    const entry = {
        id: modId,
        name: mod.name || modId,
        type: mod.generation_type,
        group: (mod.groups && mod.groups[0]) || null,
        required_level: mod.required_level || 0,
        stats: (mod.stats || []).map(s => ({
            id: s.id,
            min: s.min,
            max: s.max,
        })),
        spawn_weights: (mod.spawn_weights || [])
            .filter(w => w.weight > 0)
            .map(w => ({ tag: w.tag, weight: w.weight })),
        tags: mod.adds_tags || [],
    };
    results.push(entry);
}

// Group by mod.group to show tier structure
const byGroup = {};
for (const mod of results) {
    const key = mod.group || mod.id;
    if (!byGroup[key]) byGroup[key] = [];
    byGroup[key].push(mod);
}

// Sort tiers within each group by required_level
for (const group of Object.values(byGroup)) {
    group.sort((a, b) => a.required_level - b.required_level);
}

// Build final output
const output = {
    _meta: {
        source: 'RePoE (https://github.com/brather1ng/RePoE)',
        game: 'Path of Exile 1',
        extracted: new Date().toISOString().split('T')[0],
        total_mods: total,
        equipment_affixes: filtered,
        groups: Object.keys(byGroup).length,
        description: 'Equipment modifiers (prefix/suffix) with tier data, stat ranges, and spawn weights',
    },
    groups: byGroup,
};

// Ensure output directory exists
import { mkdirSync } from 'fs';
mkdirSync(dirname(OUTPUT), { recursive: true });

writeFileSync(OUTPUT, JSON.stringify(output, null, 2));
console.log(`Done! ${filtered}/${total} mods extracted, ${Object.keys(byGroup).length} groups`);
console.log(`Output: ${OUTPUT}`);

// Also create a summary of most common stat types
const statCount = {};
for (const mod of results) {
    for (const s of mod.stats) {
        statCount[s.id] = (statCount[s.id] || 0) + 1;
    }
}
const topStats = Object.entries(statCount)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 30);

console.log('\nTop 30 stat types:');
for (const [stat, count] of topStats) {
    console.log(`  ${stat}: ${count} mods`);
}

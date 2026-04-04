# Contributing to Lore: A Guide

Welcome to the Dungeon of Doom's lore development! This document provides guidelines for adding new stories, quests, NPCs, and world-building content.

## Before You Write

Ask yourself:
- How does this new content fit into the existing world?
- What existing factions, NPCs, or locations does it connect to?
- What era of the timeline does it occur in?
- Is there a moral or thematic depth to it, or is it purely mechanical?

Great lore has *layers*. Surface-level gameplay should hide deeper questions about the world.

## File Organization

- **World-building**: `world_history.md`, `timeline.md`
- **Characters**: `npcs_and_factions.md`
- **Creatures**: `monsters_lore.md`
- **Locations**: `regions/[region_name].md`
- **Adventures**: `quests/[quest_name].md`

## Quest Lore Template

When writing a quest narrative, use this structure:

```markdown
# [Quest Name]: [Tagline]

## Quest Giver
**Name** — Brief description of who they are

## The Quest Hook
What brings the adventurer into this story?

## The Lore
### Context (optional sections based on quest complexity)
- Historical significance
- Political intrigue
- Hidden motivations
- Mysteries or secrets

## The Dungeon/Location
Description of where the quest takes place.

## Possible Outcomes
Multiple paths or endings the quest might have.

## Rewards
- Tangible (gold, items)
- Narrative (lore unlocks, faction standing)
- Mechanical (skills, recipes)

## Connections to Larger World
How does this quest relate to other stories, NPCs, or factions?

## Themes/Moral Complexity
What makes this quest interesting beyond "kill monster, get gold"?
```

## Regional Lore Template

When adding a new region, consider:

```markdown
# [Region Name]: [Tagline]

## Geography
Where is it? What's the terrain and notable landmarks?

## Key Locations
- Dungeon entrances
- Settlements
- Points of interest
- Mysterious sites

## History & Culture
- Founding
- Major events
- Unique character
- Relationship to other regions

## Present Day
Current state and atmosphere.

## Rumors & Hooks
Plot threads that might draw adventurers here.

## Unique Mechanics
Special rules or systems that apply in this region.
```

## NPC Template

For new NPCs:

```markdown
### [Name] — [Title/Role]

**Affiliation**: Which faction or organization?
**Personality**: Brief character description
**Motivations**: What do they want?
**Secrets**: What don't they want known?
**Quest Hooks**: What might they offer adventurers?
```

## Tone & Style Guidelines

### The Dungeon of Doom is...

- **Darkly Humorous** — Danger and absurdity coexist. A farmer's magical mower quest is as valid as a battle against ancient evil.
- **Personally Motivated** — NPCs have wants, fears, and contradictions. Not everyone is pure good or evil.
- **Layered** — Surface plot hides philosophical questions about knowledge, progress, morality, and the nature of reality.
- **Interconnected** — Small stories tie into larger world events. Seemingly minor quests unlock major lore.
- **Respectful of Player Choices** — Adventurers should have multiple valid paths through stories. No "one true ending."

### Avoid...

- Grimdark nihilism (too bleak)
- High-fantasy clichés without a twist
- Moral absolutes (the world is complex)
- NPCs who exist only to give quests (they should feel like people)

## Connecting to Existing Timeline

**Important**: The current in-game date is Year 1. All lore should reference the timeline provided in `timeline.md`. If you're adding historical events, place them appropriately on the timeline.

## Cross-Referencing

When your new content connects to existing lore, use internal markdown links:
- `[The Sundering](world_history.md)` to reference world events
- `[Master Elira](npcs_and_factions.md)` to reference NPCs
- `[Buchanan](regions/buchanan.md)` to reference regions

## Reviewing Your Work

Before submitting new lore:

1. **Does it fit the tone?** Read back your work. Does it feel like Dungeon of Doom?
2. **Is it interconnected?** Have you referenced existing NPCs, factions, or events? Have you left hooks for future quests?
3. **Does it have depth?** Is there something beneath the surface? A contradiction? A moral question?
4. **Is it clear?** Have you explained enough that players understand the lore without getting bogged down?
5. **Does it respect player agency?** Are there multiple ways to engage with the content?

## Examples to Study

For inspiration, examine:
- `stolen_mower.md` — How comedy and absurdity coexist with world-building
- `bookeater_gyre.md` — How moral complexity enriches a quest
- `regions/buchanan.md` — How to introduce a location with history and intrigue

## Questions?

Lore is collaborative! If you're unsure whether something fits, that's the right time to check with other contributors or post it for feedback.

---

**Happy writing! May your stories haunt adventurers for years to come.**

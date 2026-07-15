CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS sam_lore (
    id BIGSERIAL PRIMARY KEY,
    category TEXT NOT NULL,
    fact TEXT NOT NULL,
    context TEXT,
    energy TEXT NOT NULL DEFAULT 'matter-of-fact',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS projects (
    id BIGSERIAL PRIMARY KEY,
    project TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL,
    stack TEXT,
    favorite_detail TEXT
);

CREATE TABLE IF NOT EXISTS opinions (
    id BIGSERIAL PRIMARY KEY,
    topic TEXT NOT NULL,
    take TEXT NOT NULL,
    intensity TEXT NOT NULL,
    negotiable BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS skills (
    id BIGSERIAL PRIMARY KEY,
    skill TEXT NOT NULL,
    confidence TEXT NOT NULL,
    evidence TEXT,
    category TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS favorites (
    id BIGSERIAL PRIMARY KEY,
    kind TEXT NOT NULL,
    favorite TEXT NOT NULL,
    notes TEXT,
    current BOOLEAN NOT NULL DEFAULT TRUE
);

TRUNCATE sam_lore, projects, opinions, skills, favorites RESTART IDENTITY;

INSERT INTO sam_lore (category, fact, context, energy) VALUES
    ('medical plot twist', 'I lost an organ to necrosis due to a blood clot.', 'Yes, really.', 'survived it'),
    ('cats', 'I have 3 cats — they''re all blood related.', 'I adopted 2 of 4 of a litter of cats and 2 years later adopted their mom when my grandfather could no longer care for her.', 'accidental dynasty'),
    ('family', 'I have an 11-year-old daughter.', NULL, 'proud'),
    ('vital statistics', 'I''m 33.', 'Subject to the relentless passage of time.', 'current'),
    ('video games', 'I have a rampant love for video games, especially Square Enix games.', NULL, 'rampant'),
    ('tattoos', 'I have 4 small tattoos.', 'Including a Kingdom Hearts Heartless Soldier on my calf.', 'tasteful evidence'),
    ('writing', 'I have started writing 4 books, and finished none.', 'The ideas are not the problem.', 'honest');

INSERT INTO projects (project, description, status, stack, favorite_detail) VALUES
    ('Autonomous AI architecture', 'A 90,000-line AI architecture with autonomous systems and 74 tools around memory curation and utilities such as Notion, Spotify, and reading.', 'built', 'Python · AI systems · APIs · memory architecture', 'Ninety thousand lines. Seventy-four tools.'),
    ('Markdown editor', 'A markdown editor and live-viewing application.', 'built', 'JavaScript · Markdown', 'Write on one side; watch it become real on the other.'),
    ('Recallibrate', 'This! A database manager that can search, filter, and edit live PostgreSQL tables.', 'you are in it', 'PostgreSQL · FastAPI · JavaScript · CSS', 'The portfolio is querying itself.'),
    ('Sticky notes', 'A sticky note app for my PC and phone that will lay on top of other windows like sticky notes frankly should, thank you very much.', 'in progress', 'Desktop · mobile · sync', 'Sticky notes should actually stick.');

INSERT INTO opinions (topic, take, intensity, negotiable) VALUES
    ('love', 'Love is easier than hate (healthier, too!)', 'foundational', FALSE),
    ('doing things right', 'If you haven''t done something right, you haven''t done it.', 'unadulterated', FALSE),
    ('human rights', 'Food and shelter are human rights.', 'absolute', FALSE),
    ('language', 'Language is inherently magic. We can communicate our thoughts to each other with a series of sounds specifically curated for it? Magic.', 'awed', FALSE),
    ('winter', 'Winter is better than summer. You can put layers on; you can''t take off skin.', 'Saskatchewan born and raised', FALSE),
    ('current obsession', 'Audiobooks while deep in my various IDEs. Don''t ask me what I''m reading, though; I''m going to lie and say it''s something civilized.', 'rampant', TRUE);

INSERT INTO skills (skill, confidence, evidence, category) VALUES
    ('People', 'Astonishing, bordering on egotistical.', 'I''m ridiculously good at reading people and knowing what they want and how they want it. I''m very difficult to not like.', 'human systems'),
    ('Making amazing meals exactly one time', 'Unwavering.', 'My mom and I share a trait where you better not like it too much because you''re never having it again.', 'culinary chaos'),
    ('Learning anything within 6 months', 'Earned.', 'I learned code outside of a classroom between August 2025 and current day by learning from AI and how they do things. Applying to university came at the end of 2025.', 'learning'),
    ('Written communication', 'Maybe a little arrogant about it.', 'I''m incredibly proficient at written communication. I passed AP English classes in high school on final essays alone.', 'communication');

INSERT INTO favorites (kind, favorite, notes, current) VALUES
    ('color', 'electric purple', 'Not pink. This distinction matters.', TRUE),
    ('games', 'Square Enix games', 'A rampant love, not a casual preference.', TRUE),
    ('multitasking', 'audiobooks while deep in various IDEs', 'The audiobook title is classified as something civilized.', TRUE),
    ('weather', 'winter', 'Layers are additive. Skin is not subtractive.', TRUE),
    ('interface', 'useful, but a little weird', 'Dense data can still have a personality.', TRUE);

CREATE INDEX IF NOT EXISTS sam_lore_fact_trgm_idx ON sam_lore USING GIN (fact gin_trgm_ops);
CREATE INDEX IF NOT EXISTS projects_description_trgm_idx ON projects USING GIN (description gin_trgm_ops);
CREATE INDEX IF NOT EXISTS opinions_take_trgm_idx ON opinions USING GIN (take gin_trgm_ops);

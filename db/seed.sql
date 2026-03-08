-- PULSE — Seed data for demo
-- 20 fake London events across 5 categories

CREATE TABLE IF NOT EXISTS users (
  id VARCHAR(64) PRIMARY KEY,
  display_name VARCHAR(128) NOT NULL,
  location VARCHAR(128) NOT NULL DEFAULT 'London',
  ai_enabled BOOLEAN NOT NULL DEFAULT true,
  ai_opt_out_reason VARCHAR(64),
  preferences JSONB NOT NULL DEFAULT '{"categories": [], "times": [], "radius_km": 10}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS events (
  id VARCHAR(64) PRIMARY KEY,
  title VARCHAR(256) NOT NULL,
  description TEXT NOT NULL,
  category VARCHAR(64) NOT NULL,
  venue VARCHAR(256) NOT NULL,
  address VARCHAR(256) NOT NULL,
  city VARCHAR(128) NOT NULL DEFAULT 'London',
  date TIMESTAMPTZ NOT NULL,
  price_gbp NUMERIC(10,2),
  image_url VARCHAR(512),
  tags TEXT[] NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS saved_events (
  user_id VARCHAR(64) NOT NULL REFERENCES users(id),
  event_id VARCHAR(64) NOT NULL REFERENCES events(id),
  saved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (user_id, event_id)
);

CREATE TABLE IF NOT EXISTS ai_opt_out_log (
  id SERIAL PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL REFERENCES users(id),
  reason VARCHAR(64),
  session_count INTEGER,
  last_ai_response_ms INTEGER,
  opted_out_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Demo user
INSERT INTO users (id, display_name, location, preferences) VALUES
('demo_user', 'Demo User', 'London', '{"categories": ["music", "food"], "times": ["evening", "weekend"], "radius_km": 10}')
ON CONFLICT (id) DO NOTHING;

-- Events: Music (4)
INSERT INTO events (id, title, description, category, venue, address, city, date, price_gbp, tags) VALUES
('evt_001', 'Jazz & Soul Night', 'An intimate evening of live jazz and soul at one of London''s most beloved underground venues. Featuring the Marcus Cole Quartet.', 'music', 'Ronnie Scott''s', '47 Frith St, Soho, London W1D 4HT', 'London', NOW() + INTERVAL '2 days', 25.00, ARRAY['jazz', 'live music', 'evening']),
('evt_002', 'Indie Rock Showcase', 'Five emerging indie bands battle it out on the Brixton stage. Doors open at 7pm.', 'music', 'O2 Academy Brixton', 'Stockwell Rd, Brixton, London SW9 9SL', 'London', NOW() + INTERVAL '3 days', 18.00, ARRAY['indie', 'rock', 'live music']),
('evt_003', 'Classical at the Barbican', 'The London Symphony Orchestra performs Beethoven''s 9th Symphony. A night of transcendence.', 'music', 'Barbican Centre', 'Silk St, Barbican, London EC2Y 8DS', 'London', NOW() + INTERVAL '5 days', 45.00, ARRAY['classical', 'orchestra', 'evening']),
('evt_004', 'Electronic Music Festival', 'Three floors of electronic music featuring Berlin and London''s finest DJs. 10pm till late.', 'music', 'Fabric London', '77a Charterhouse St, Farringdon, London EC1M 3HN', 'London', NOW() + INTERVAL '7 days', 20.00, ARRAY['electronic', 'dance', 'late night']);

-- Events: Food (4)
INSERT INTO events (id, title, description, category, venue, address, city, date, price_gbp, tags) VALUES
('evt_005', 'Street Food Market', 'Over 40 street food vendors from around the world. Vegetarian and vegan options galore.', 'food', 'Borough Market', '8 Southwark St, London SE1 1TL', 'London', NOW() + INTERVAL '1 day', 0.00, ARRAY['street food', 'market', 'vegan friendly']),
('evt_006', 'Wine Tasting: Natural Wines', 'Explore 20+ natural and biodynamic wines from small European producers. Expert-led sessions every hour.', 'food', 'Vinoteca Soho', '53-55 Beak St, Soho, London W1F 9SH', 'London', NOW() + INTERVAL '4 days', 35.00, ARRAY['wine', 'tasting', 'evening']),
('evt_007', 'Sushi Masterclass', 'Learn to make authentic nigiri and maki with head chef Hiroshi Tanaka. Includes dinner.', 'food', 'Zuma Restaurant', '5 Raphael St, Knightsbridge, London SW7 1DL', 'London', NOW() + INTERVAL '6 days', 95.00, ARRAY['sushi', 'cooking class', 'japanese']),
('evt_008', 'London Food Festival', 'The annual celebration of London''s diverse food scene. Demos, tastings, and pop-ups.', 'food', 'Southbank Centre', 'Belvedere Rd, London SE1 8XX', 'London', NOW() + INTERVAL '10 days', 0.00, ARRAY['festival', 'food', 'family friendly']);

-- Events: Art (4)
INSERT INTO events (id, title, description, category, venue, address, city, date, price_gbp, tags) VALUES
('evt_009', 'Tate Modern: AI & Art', 'A groundbreaking exhibition exploring the intersection of artificial intelligence and contemporary art.', 'art', 'Tate Modern', 'Bankside, London SE1 9TG', 'London', NOW() + INTERVAL '1 day', 22.00, ARRAY['exhibition', 'ai', 'contemporary']),
('evt_010', 'East End Gallery Night', 'Shoreditch and Bethnal Green galleries open late with new exhibitions, drinks, and artist talks.', 'art', 'Various Venues', 'Shoreditch, London E1', 'London', NOW() + INTERVAL '3 days', 0.00, ARRAY['galleries', 'free', 'east london']),
('evt_011', 'Photography Workshop', 'Street photography masterclass with award-winning photographer Leila Nour. Limited to 12 participants.', 'art', 'The Photographers Gallery', '16-18 Ramillies St, London W1F 7LW', 'London', NOW() + INTERVAL '8 days', 75.00, ARRAY['photography', 'workshop', 'street art']),
('evt_012', 'Sculpture in the City', 'Annual outdoor sculpture trail through the City of London. Self-guided with audio tour.', 'art', 'City of London', 'Various locations, London EC2', 'London', NOW() + INTERVAL '2 days', 0.00, ARRAY['sculpture', 'outdoor', 'free']);

-- Events: Sport (4)
INSERT INTO events (id, title, description, category, venue, address, city, date, price_gbp, tags) VALUES
('evt_013', 'Premier League: Arsenal vs Chelsea', 'The North London derby meets West London in this crucial Premier League clash.', 'sport', 'Emirates Stadium', 'Holloway Rd, London N7 7AJ', 'London', NOW() + INTERVAL '4 days', 65.00, ARRAY['football', 'premier league', 'derby']),
('evt_014', 'London Marathon Training Run', 'Community 10K training run through Hyde Park. All paces welcome. Free post-run coffee.', 'sport', 'Hyde Park', 'Hyde Park, London W2 2UH', 'London', NOW() + INTERVAL '2 days', 0.00, ARRAY['running', 'community', 'free']),
('evt_015', 'Yoga in the Park', 'Sunrise yoga session in Regent''s Park led by certified instructor. Mats provided.', 'sport', 'Regent''s Park', 'Regent''s Park, London NW1 4NR', 'London', NOW() + INTERVAL '1 day', 12.00, ARRAY['yoga', 'outdoor', 'morning']),
('evt_016', 'Boxing Night at York Hall', 'Professional boxing evening featuring six bouts. Doors 6pm, first bout 7:30pm.', 'sport', 'York Hall', '5 Old Ford Rd, Bethnal Green, London E2 9PJ', 'London', NOW() + INTERVAL '6 days', 30.00, ARRAY['boxing', 'evening', 'east london']);

-- Events: Tech (4)
INSERT INTO events (id, title, description, category, venue, address, city, date, price_gbp, tags) VALUES
('evt_017', 'London AI Meetup', 'Monthly gathering of AI practitioners and enthusiasts. Lightning talks, demos, and networking.', 'tech', 'Google Campus London', '4-5 Bonhill St, London EC2A 4BX', 'London', NOW() + INTERVAL '5 days', 0.00, ARRAY['ai', 'meetup', 'networking', 'free']),
('evt_018', 'Kubernetes & Cloud Native Summit', 'Full-day conference on K8s, GitOps, and platform engineering. 20+ talks from industry experts.', 'tech', 'ExCeL London', 'Royal Victoria Dock, London E16 1XL', 'London', NOW() + INTERVAL '9 days', 149.00, ARRAY['kubernetes', 'devops', 'conference']),
('evt_019', 'Startup Pitch Night', 'Ten early-stage startups pitch to a panel of London VCs. Networking drinks included.', 'tech', 'Level39', 'One Canada Square, Canary Wharf, London E14 5AB', 'London', NOW() + INTERVAL '3 days', 0.00, ARRAY['startup', 'vc', 'networking', 'free']),
('evt_020', 'Observability & SRE Workshop', 'Hands-on full-day workshop covering distributed tracing, alerting, and incident response.', 'tech', 'Skills Matter', '10 South Place, London EC2M 7EB', 'London', NOW() + INTERVAL '7 days', 199.00, ARRAY['observability', 'sre', 'workshop', 'devops']);

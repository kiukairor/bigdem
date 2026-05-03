-- PULSE — Seed data for demo
-- 20 London events + 20 Paris events across 5 categories

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
  ticket_url VARCHAR(512) NOT NULL DEFAULT '',
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

-- Paris Events: Music (4)
INSERT INTO events (id, title, description, category, venue, address, city, date, price_gbp, tags) VALUES
('evt_p001', 'Jazz au Duc des Lombards', 'An intimate evening of bebop and modern jazz at Paris''s most celebrated jazz club. Featuring the Émile Renard Trio.', 'music', 'Duc des Lombards', '42 Rue des Lombards, 75001 Paris', 'Paris', NOW() + INTERVAL '2 days', 28.00, ARRAY['jazz', 'live music', 'evening']),
('evt_p002', 'Electronic Night at Rex Club', 'Paris''s legendary underground techno club hosts an all-night session with Berlin and Paris headliners.', 'music', 'Rex Club', '5 Boulevard Poissonnière, 75002 Paris', 'Paris', NOW() + INTERVAL '4 days', 22.00, ARRAY['electronic', 'techno', 'late night']),
('evt_p003', 'Philharmonie de Paris: Debussy', 'The Orchestre de Paris performs Debussy''s La Mer and Ravel''s Boléro. A defining night of French classical music.', 'music', 'Philharmonie de Paris', '221 Avenue Jean Jaurès, 75019 Paris', 'Paris', NOW() + INTERVAL '6 days', 55.00, ARRAY['classical', 'orchestra', 'evening']),
('evt_p004', 'Nuit de la Chanson Française', 'A tribute evening celebrating the great chansonniers — Brel, Piaf, Gainsbourg — performed by today''s finest voices.', 'music', 'La Cigale', '120 Boulevard de Rochechouart, 75018 Paris', 'Paris', NOW() + INTERVAL '8 days', 32.00, ARRAY['chanson', 'french music', 'evening']);

-- Paris Events: Food (4)
INSERT INTO events (id, title, description, category, venue, address, city, date, price_gbp, tags) VALUES
('evt_p005', 'Marché des Enfants Rouges', 'Explore Paris''s oldest covered market. Fresh produce, Moroccan street food, Italian antipasti, and the best crêpes in the Marais.', 'food', 'Marché des Enfants Rouges', '39 Rue de Bretagne, 75003 Paris', 'Paris', NOW() + INTERVAL '1 day', 0.00, ARRAY['market', 'street food', 'free']),
('evt_p006', 'Fromage & Vin en Saint-Germain', 'A guided tasting of 12 artisan French cheeses paired with natural wines from the Loire and Burgundy. Expert sommelier led.', 'food', 'Fromagerie Laurent Dubois', '2 Rue de Lourmel, 75015 Paris', 'Paris', NOW() + INTERVAL '5 days', 48.00, ARRAY['cheese', 'wine', 'tasting', 'evening']),
('evt_p007', 'Viennoiserie Masterclass', 'Learn the art of croissant and pain au chocolat from a Meilleur Ouvrier de France pastry chef. Includes breakfast.', 'food', 'École Ferrandi Paris', '28 Rue de l''Abbé Grégoire, 75006 Paris', 'Paris', NOW() + INTERVAL '3 days', 110.00, ARRAY['pastry', 'cooking class', 'morning']),
('evt_p008', 'Fête de la Gastronomie', 'The annual celebration of French cuisine returns to the Seine banks. Chef demos, tastings, and pop-ups from 3-star restaurants.', 'food', 'Quai Branly', 'Quai Branly, 75007 Paris', 'Paris', NOW() + INTERVAL '9 days', 0.00, ARRAY['festival', 'food', 'free', 'family friendly']);

-- Paris Events: Art (4)
INSERT INTO events (id, title, description, category, venue, address, city, date, price_gbp, tags) VALUES
('evt_p009', 'Louvre: Nocturne Impressionnisme', 'The Louvre opens late for a guided tour of its Impressionist collection. Champagne reception included.', 'art', 'Musée du Louvre', 'Rue de Rivoli, 75001 Paris', 'Paris', NOW() + INTERVAL '3 days', 38.00, ARRAY['exhibition', 'impressionism', 'evening']),
('evt_p010', 'Promenade des Galeries — Montmartre', 'A self-guided evening walk through Montmartre''s hidden ateliers and galleries. Meet the artists behind the work.', 'art', 'Various Venues', 'Montmartre, 75018 Paris', 'Paris', NOW() + INTERVAL '2 days', 0.00, ARRAY['galleries', 'free', 'montmartre']),
('evt_p011', 'Street Art Tour Belleville', 'Expert-guided 3-hour walk through Belleville''s world-famous street art scene. From Shepard Fairey to local legends.', 'art', 'Parc de Belleville', '47 Rue des Couronnes, 75020 Paris', 'Paris', NOW() + INTERVAL '7 days', 20.00, ARRAY['street art', 'tour', 'outdoor']),
('evt_p012', 'Centre Pompidou: Art & IA', 'A landmark exhibition at the Pompidou exploring how artificial intelligence is reshaping contemporary art practice.', 'art', 'Centre Pompidou', 'Place Georges-Pompidou, 75004 Paris', 'Paris', NOW() + INTERVAL '1 day', 18.00, ARRAY['ai', 'contemporary', 'exhibition']);

-- Paris Events: Sport (4)
INSERT INTO events (id, title, description, category, venue, address, city, date, price_gbp, tags) VALUES
('evt_p013', 'PSG vs Olympique de Marseille', 'Le Classique returns to the Parc des Princes. The biggest rivalry in French football.', 'sport', 'Parc des Princes', '24 Rue du Commandant Guilbaud, 75016 Paris', 'Paris', NOW() + INTERVAL '5 days', 72.00, ARRAY['football', 'ligue 1', 'classique']),
('evt_p014', 'Course de la Seine — 10K', 'Community 10K run along the banks of the Seine from Pont de l''Alma to Pont de Bir-Hakeim. All levels welcome.', 'sport', 'Pont de l''Alma', 'Pont de l''Alma, 75008 Paris', 'Paris', NOW() + INTERVAL '3 days', 0.00, ARRAY['running', 'community', 'free']),
('evt_p015', 'Yoga aux Tuileries', 'Morning yoga in the Tuileries Garden with certified instructor Marie Leclerc. Mats provided, all levels welcome.', 'sport', 'Jardin des Tuileries', 'Place de la Concorde, 75001 Paris', 'Paris', NOW() + INTERVAL '1 day', 14.00, ARRAY['yoga', 'outdoor', 'morning']),
('evt_p016', 'Cyclisme — Tour du Bois de Vincennes', 'Guided cycling tour around the Bois de Vincennes with the Paris Cycling Club. 25km, bikes available to hire.', 'sport', 'Bois de Vincennes', 'Bois de Vincennes, 75012 Paris', 'Paris', NOW() + INTERVAL '4 days', 15.00, ARRAY['cycling', 'outdoor', 'weekend']);

-- Paris Events: Tech (4)
INSERT INTO events (id, title, description, category, venue, address, city, date, price_gbp, tags) VALUES
('evt_p017', 'Paris AI Meetup — Station F', 'Monthly gathering of Paris''s AI community at Europe''s largest startup campus. Demos, talks, and networking.', 'tech', 'Station F', '5 Parvis Alan Turing, 75013 Paris', 'Paris', NOW() + INTERVAL '6 days', 0.00, ARRAY['ai', 'meetup', 'networking', 'free']),
('evt_p018', 'VivaTech 2026 — Day Pass', 'Europe''s largest startup and tech conference returns to Porte de Versailles. 100,000 attendees, 450+ startups.', 'tech', 'Paris Expo Porte de Versailles', 'Place de la Porte de Versailles, 75015 Paris', 'Paris', NOW() + INTERVAL '10 days', 180.00, ARRAY['conference', 'startup', 'innovation']),
('evt_p019', 'French Tech Pitch Night', 'Eight deep-tech startups pitch to a panel of French and European VCs. Drinks and networking follow.', 'tech', 'BPI France', '6-8 Boulevard Haussmann, 75009 Paris', 'Paris', NOW() + INTERVAL '4 days', 0.00, ARRAY['startup', 'pitch', 'networking', 'free']),
('evt_p020', 'Kubernetes & Platform Engineering Paris', 'Full-day summit on cloud-native architecture, GitOps, and platform engineering best practices. Hosted by CNCF France.', 'tech', 'Palais des Congrès', '2 Place de la Porte Maillot, 75017 Paris', 'Paris', NOW() + INTERVAL '8 days', 160.00, ARRAY['kubernetes', 'devops', 'platform engineering', 'conference']);

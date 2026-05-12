// agent-brain schema. Idempotent — safe to re-run.

CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE;
CREATE CONSTRAINT memory_path IF NOT EXISTS FOR (m:Memory) REQUIRE m.path IS UNIQUE;
CREATE CONSTRAINT topic_name IF NOT EXISTS FOR (t:Topic) REQUIRE t.name IS UNIQUE;

CREATE CONSTRAINT session_id IF NOT EXISTS FOR (s:Session) REQUIRE s.session_id IS UNIQUE;
CREATE CONSTRAINT event_id IF NOT EXISTS FOR (e:Event) REQUIRE e.event_id IS UNIQUE;

CREATE CONSTRAINT plan_id IF NOT EXISTS FOR (p:Plan) REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT step_id IF NOT EXISTS FOR (st:Step) REQUIRE st.id IS UNIQUE;

CREATE CONSTRAINT flow_id IF NOT EXISTS FOR (f:Flow) REQUIRE f.id IS UNIQUE;
CREATE CONSTRAINT fire_id IF NOT EXISTS FOR (fi:Fire) REQUIRE fi.id IS UNIQUE;

CREATE INDEX memory_updated IF NOT EXISTS FOR (m:Memory) ON (m.updated_at);
CREATE INDEX event_ts IF NOT EXISTS FOR (e:Event) ON (e.timestamp);
CREATE INDEX fire_at IF NOT EXISTS FOR (fi:Fire) ON (fi.at);

CREATE FULLTEXT INDEX memory_fulltext IF NOT EXISTS FOR (m:Memory) ON EACH [m.content, m.path];

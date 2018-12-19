-- SPDX-License-Identifier: MIT
-- Copyright (c) 2017 William Pitcock
-- Copyright (c) 2018 Max Rees
-- See LICENSE for more information.
--
-- PostgreSQL database dump
--
-- Dumped from database version 10.1
-- Dumped by pg_dump version 10.1

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SET check_function_bodies = false;
SET client_min_messages = warning;
SET row_security = off;
SET search_path = public, pg_catalog;
SET default_tablespace = '';
SET default_with_oids = false;

--
-- Name: plpgsql; Type: EXTENSION; Schema: -; Owner: 
--
CREATE EXTENSION IF NOT EXISTS plpgsql WITH SCHEMA pg_catalog;

--
-- Name: EXTENSION plpgsql; Type: COMMENT; Schema: -; Owner: 
--
COMMENT ON EXTENSION plpgsql IS 'PL/pgSQL procedural language';


CREATE OR REPLACE FUNCTION update_timestamp_col()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

--
-- Name: status_enum; Type: TYPE; Schema: public; Owner: postgres
--
CREATE TYPE status_enum AS ENUM (
    'new',
    'rejected',
    'building',
    'success',
    'error',
    'failure'
);
ALTER TYPE status_enum OWNER TO postgres;

--
-- Name: event_category_enum; Type: TYPE; Schema: public; Owner: postgres
--
CREATE TYPE event_category_enum AS ENUM (
    'push',
    'merge_request',
    'note',
    'irc',
    'manual'
);
ALTER TYPE event_category_enum OWNER TO postgres;


--
-- Name: event; Type: TABLE; Schema: public; Owner: postgres
--
CREATE TABLE event (
    id integer NOT NULL,
    created timestamptz NOT NULL DEFAULT NOW(),
    updated timestamptz NOT NULL DEFAULT NOW(),
    category event_category_enum NOT NULL,
    status status_enum DEFAULT 'new'::status_enum NOT NULL,
    shortmsg text,
    msg text,
    project character varying(255) NOT NULL,
    url character varying(255) NOT NULL,
    branch character varying(255) DEFAULT 'master'::character varying NOT NULL,
    commit_id character varying(40) NOT NULL,
    mr_id integer NOT NULL DEFAULT 0,
    username character varying(255) NOT NULL
);
ALTER TABLE event OWNER TO postgres;

--
-- Name: event_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--
CREATE SEQUENCE event_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER TABLE event_id_seq OWNER TO postgres;

--
-- Name: event_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--
ALTER SEQUENCE event_id_seq OWNED BY event.id;

--
-- Name: event id; Type: DEFAULT; Schema: public; Owner: postgres
--
ALTER TABLE ONLY event ALTER COLUMN id SET DEFAULT nextval('event_id_seq'::regclass);

--
-- Name: event event_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--
ALTER TABLE ONLY event
    ADD CONSTRAINT event_pkey PRIMARY KEY (id);

CREATE TRIGGER event_update_timestamp BEFORE UPDATE
    ON event FOR EACH ROW EXECUTE PROCEDURE update_timestamp_col();


--
-- Name: job; Type: TABLE; Schema: public; Owner: postgres
--
CREATE TABLE job (
    id integer NOT NULL,
    created timestamptz NOT NULL DEFAULT NOW(),
    updated timestamptz NOT NULL DEFAULT NOW(),
    event_id integer NOT NULL,
    status status_enum DEFAULT 'new'::status_enum NOT NULL,
    shortmsg text,
    msg text,
    priority integer NOT NULL,
    arch character varying(255) NOT NULL
);
ALTER TABLE job OWNER TO postgres;

--
-- Name: job_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--
CREATE SEQUENCE job_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER TABLE job_id_seq OWNER TO postgres;

--
-- Name: job_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--
ALTER SEQUENCE job_id_seq OWNED BY job.id;

--
-- Name: job id; Type: DEFAULT; Schema: public; Owner: postgres
--
ALTER TABLE ONLY job ALTER COLUMN id SET DEFAULT nextval('job_id_seq'::regclass);

--
-- Name: job job_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--
ALTER TABLE ONLY job
    ADD CONSTRAINT job_pkey PRIMARY KEY (id);

--
-- Name: job job_event_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--
ALTER TABLE ONLY job
    ADD CONSTRAINT job_event_id_fkey FOREIGN KEY (event_id) REFERENCES event(id);

CREATE TRIGGER job_update_timestamp BEFORE UPDATE
    ON job FOR EACH ROW EXECUTE PROCEDURE update_timestamp_col();


--
-- Name: task; Type: TABLE; Schema: public; Owner: postgres
--
CREATE TABLE task (
    id integer NOT NULL,
    job_id integer NOT NULL,
    status status_enum DEFAULT 'new'::status_enum NOT NULL,
    created timestamptz NOT NULL DEFAULT NOW(),
    updated timestamptz NOT NULL DEFAULT NOW(),
    shortmsg text,
    msg text,
    package character varying(255) NOT NULL,
    version character varying(255) NOT NULL,
    maintainer character varying(255)
);
ALTER TABLE task OWNER TO postgres;

--
-- Name: task_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--
CREATE SEQUENCE task_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER TABLE task_id_seq OWNER TO postgres;

--
-- Name: task_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--
ALTER SEQUENCE task_id_seq OWNED BY task.id;

--
-- Name: task id; Type: DEFAULT; Schema: public; Owner: postgres
--
ALTER TABLE ONLY task ALTER COLUMN id SET DEFAULT nextval('task_id_seq'::regclass);

--
-- Name: task task_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--
ALTER TABLE ONLY task
    ADD CONSTRAINT task_pkey PRIMARY KEY (id);

--
-- Name: task task_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--
ALTER TABLE ONLY task
    ADD CONSTRAINT task_job_id_fkey FOREIGN KEY (job_id) REFERENCES job(id);

CREATE TRIGGER task_update_timestamp BEFORE UPDATE
    ON task FOR EACH ROW EXECUTE PROCEDURE update_timestamp_col();


--
-- Name: job_artifact; Type: TABLE; Schema: public; Owner: postgres
--
CREATE TABLE job_artifact (
    job_artifact_id integer NOT NULL,
    job_id integer,
    filename character varying(4096)
);
ALTER TABLE job_artifact OWNER TO postgres;

--
-- Name: job_artifact_job_artifact_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--
CREATE SEQUENCE job_artifact_job_artifact_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER TABLE job_artifact_job_artifact_id_seq OWNER TO postgres;

--
-- Name: job_artifact_job_artifact_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--
ALTER SEQUENCE job_artifact_job_artifact_id_seq OWNED BY job_artifact.job_artifact_id;

--
-- Name: job_artifact job_artifact_id; Type: DEFAULT; Schema: public; Owner: postgres
--
ALTER TABLE ONLY job_artifact ALTER COLUMN job_artifact_id SET DEFAULT nextval('job_artifact_job_artifact_id_seq'::regclass);

--
-- Name: job_artifact job_artifact_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--
ALTER TABLE ONLY job_artifact
    ADD CONSTRAINT job_artifact_pkey PRIMARY KEY (job_artifact_id);

--
-- Name: job_artifact job_artifact_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--
ALTER TABLE ONLY job_artifact
    ADD CONSTRAINT job_artifact_job_id_fkey FOREIGN KEY (job_id) REFERENCES job(id);


--
-- Name: job_dependency; Type: TABLE; Schema: public; Owner: postgres
--
CREATE TABLE job_dependency (
    job_dependency_id integer NOT NULL,
    job_id integer,
    dependent_id integer
);
ALTER TABLE job_dependency OWNER TO postgres;

--
-- Name: job_dependency_job_dependency_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--
CREATE SEQUENCE job_dependency_job_dependency_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER TABLE job_dependency_job_dependency_id_seq OWNER TO postgres;

--
-- Name: job_dependency_job_dependency_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--
ALTER SEQUENCE job_dependency_job_dependency_id_seq OWNED BY job_dependency.job_dependency_id;

--
-- Name: job_dependency job_dependency_id; Type: DEFAULT; Schema: public; Owner: postgres
--
ALTER TABLE ONLY job_dependency ALTER COLUMN job_dependency_id SET DEFAULT nextval('job_dependency_job_dependency_id_seq'::regclass);

--
-- Name: job_dependency job_dependency_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--
ALTER TABLE ONLY job_dependency
    ADD CONSTRAINT job_dependency_pkey PRIMARY KEY (job_dependency_id);

--
-- Name: job_dependency job_dependency_dependent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--
ALTER TABLE ONLY job_dependency
    ADD CONSTRAINT job_dependency_dependent_id_fkey FOREIGN KEY (dependent_id) REFERENCES job(id);

--
-- Name: job_dependency job_dependency_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--
ALTER TABLE ONLY job_dependency
    ADD CONSTRAINT job_dependency_job_id_fkey FOREIGN KEY (job_id) REFERENCES job(id);


--
-- PostgreSQL database dump complete
--

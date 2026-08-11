"""enterprise memory lifecycle and forgetting v1

Revision ID: 0021_memory_lifecycle_v1
Revises: 0020_enterprise_memory_core_v1
Create Date: 2026-08-10
"""
from __future__ import annotations

from alembic import op


revision = "0021_memory_lifecycle_v1"
down_revision = "0020_enterprise_memory_core_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE ai_memory_records DROP CONSTRAINT ck_ai_memory_status;
        ALTER TABLE ai_memory_records
          ADD COLUMN last_used_at TIMESTAMPTZ,
          ADD COLUMN usage_count INTEGER NOT NULL DEFAULT 0,
          ADD COLUMN soft_deleted_at TIMESTAMPTZ,
          ADD COLUMN delete_requested_at TIMESTAMPTZ,
          ADD CONSTRAINT ck_ai_memory_status CHECK (
            status IN ('draft','pending','active','cold','archived','delete_pending','deleted')
          ),
          ADD CONSTRAINT ck_ai_memory_usage_count CHECK (usage_count >= 0);

        ALTER TABLE ai_memory_outbox DROP CONSTRAINT ck_ai_memory_outbox_status;
        ALTER TABLE ai_memory_outbox ADD CONSTRAINT ck_ai_memory_outbox_status
          CHECK (status IN ('pending','processing','processed','failed','dead_letter'));

        ALTER TABLE ai_memory_usage DROP CONSTRAINT ai_memory_usage_memory_id_fkey;
        ALTER TABLE ai_memory_usage DROP CONSTRAINT ai_memory_usage_version_id_fkey;
        ALTER TABLE ai_memory_outbox DROP CONSTRAINT ai_memory_outbox_memory_id_fkey;
        ALTER TABLE ai_memory_admissions DROP CONSTRAINT ai_memory_admissions_memory_id_fkey;
        ALTER TABLE ai_memory_state_transitions DROP CONSTRAINT ai_memory_state_transitions_memory_id_fkey;

        CREATE TABLE ai_memory_legal_holds (
          hold_id VARCHAR(72) PRIMARY KEY,
          memory_id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          workspace_id VARCHAR(64) NOT NULL,
          user_id VARCHAR(128) NOT NULL,
          agent_id VARCHAR(64) NOT NULL,
          reason TEXT NOT NULL,
          active BOOLEAN NOT NULL DEFAULT TRUE,
          placed_by_run_id VARCHAR(128) NOT NULL,
          placed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
          released_by_run_id VARCHAR(128),
          released_at TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX uq_ai_memory_active_hold ON ai_memory_legal_holds(memory_id) WHERE active;
        CREATE INDEX idx_ai_memory_hold_scope ON ai_memory_legal_holds(
          tenant_id,workspace_id,user_id,agent_id,memory_id,active
        );

        CREATE TABLE ai_memory_deletion_jobs (
          job_id VARCHAR(72) PRIMARY KEY,
          memory_id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          workspace_id VARCHAR(64) NOT NULL,
          user_id VARCHAR(128) NOT NULL,
          agent_id VARCHAR(64) NOT NULL,
          status VARCHAR(20) NOT NULL DEFAULT 'pending',
          requested_by VARCHAR(128) NOT NULL,
          admin_authorized BOOLEAN NOT NULL DEFAULT FALSE,
          attempt_count INTEGER NOT NULL DEFAULT 0,
          max_attempts INTEGER NOT NULL DEFAULT 5,
          result JSONB NOT NULL DEFAULT '{}'::jsonb,
          last_error TEXT,
          idempotency_key VARCHAR(160) NOT NULL UNIQUE,
          requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
          started_at TIMESTAMPTZ,
          completed_at TIMESTAMPTZ,
          CONSTRAINT ck_ai_memory_delete_job_status CHECK (
            status IN ('pending','running','partial','completed','failed','blocked')
          ),
          CONSTRAINT ck_ai_memory_delete_attempts CHECK (
            attempt_count >= 0 AND max_attempts BETWEEN 1 AND 20
          )
        );
        CREATE INDEX idx_ai_memory_delete_job_dispatch ON ai_memory_deletion_jobs(status,requested_at);

        CREATE TABLE ai_memory_deletion_proofs (
          proof_id VARCHAR(72) PRIMARY KEY,
          job_id VARCHAR(72) NOT NULL UNIQUE REFERENCES ai_memory_deletion_jobs(job_id),
          memory_id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          workspace_id VARCHAR(64) NOT NULL,
          user_id VARCHAR(128) NOT NULL,
          agent_id VARCHAR(64) NOT NULL,
          content_hash CHAR(64) NOT NULL,
          version_set_hash VARCHAR(64) NOT NULL,
          results JSONB NOT NULL,
          deleted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX idx_ai_memory_deletion_proof_scope ON ai_memory_deletion_proofs(
          tenant_id,workspace_id,user_id,agent_id,memory_id,deleted_at DESC
        );
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION ai_memory_purge(p_job_id VARCHAR, p_event_id VARCHAR)
        RETURNS JSONB
        LANGUAGE plpgsql SECURITY DEFINER SET search_path FROM CURRENT AS $$
        DECLARE
          j ai_memory_deletion_jobs%ROWTYPE;
          r ai_memory_records%ROWTYPE;
          relation_count INTEGER := 0;
          outbox_count INTEGER := 0;
          version_count INTEGER := 0;
          version_hash VARCHAR(64) := '';
          proof JSONB;
        BEGIN
          SELECT * INTO j FROM ai_memory_deletion_jobs WHERE job_id=p_job_id FOR UPDATE;
          IF NOT FOUND THEN RAISE EXCEPTION 'deletion_job_not_found'; END IF;
          SELECT jsonb_build_object('proof_id',proof_id,'job_id',job_id,'memory_id',memory_id,'results',results)
            INTO proof FROM ai_memory_deletion_proofs WHERE job_id=p_job_id;
          IF proof IS NOT NULL THEN RETURN proof; END IF;
          SELECT * INTO r FROM ai_memory_records WHERE memory_id=j.memory_id FOR UPDATE;
          IF NOT FOUND THEN RAISE EXCEPTION 'memory_record_missing_without_proof'; END IF;
          IF NOT EXISTS (
            SELECT 1 FROM ai_memory_outbox WHERE event_id=p_event_id AND memory_id=j.memory_id
              AND event_type='MEMORY_DELETE_REQUESTED' AND status='processing'
          ) THEN RAISE EXCEPTION 'deletion_event_not_authorized'; END IF;
          IF EXISTS (SELECT 1 FROM ai_memory_legal_holds WHERE memory_id=j.memory_id AND active) THEN
            RAISE EXCEPTION 'legal_hold_active';
          END IF;
          SELECT COALESCE(md5(string_agg(content_hash::text,',' ORDER BY version_no)),'')
            INTO version_hash FROM ai_memory_versions WHERE memory_id=j.memory_id;
          DELETE FROM ai_memory_relations
            WHERE source_memory_id=j.memory_id OR target_memory_id=j.memory_id;
          GET DIAGNOSTICS relation_count = ROW_COUNT;
          DELETE FROM ai_memory_outbox WHERE memory_id=j.memory_id AND event_id<>p_event_id;
          GET DIAGNOSTICS outbox_count = ROW_COUNT;
          DELETE FROM ai_memory_versions WHERE memory_id=j.memory_id;
          GET DIAGNOSTICS version_count = ROW_COUNT;
          DELETE FROM ai_memory_records WHERE memory_id=j.memory_id;
          proof := jsonb_build_object(
            'record','deleted','versions_deleted',version_count,
            'relations_deleted',relation_count,'outbox_superseded',outbox_count,
            'usage_audit','retained_without_content_fk','admission_audit','retained_without_content_fk',
            'state_audit','retained_without_content_fk','vector','not_applicable_current_v1',
            'search_index','not_applicable_current_v1','cache','not_applicable_no_memory_cache',
            'context_summary','database_retrieval_excludes_deleted_record'
          );
          INSERT INTO ai_memory_deletion_proofs(
            proof_id,job_id,memory_id,tenant_id,workspace_id,user_id,agent_id,
            content_hash,version_set_hash,results
          ) VALUES (
            'memproof_'||replace(gen_random_uuid()::text,'-',''),j.job_id,j.memory_id,
            j.tenant_id,j.workspace_id,j.user_id,j.agent_id,r.content_hash,version_hash,proof
          );
          UPDATE ai_memory_deletion_jobs SET status='completed',result=proof,last_error=NULL,
            completed_at=CURRENT_TIMESTAMP WHERE job_id=j.job_id;
          RETURN proof;
        END $$;
        REVOKE ALL ON FUNCTION ai_memory_purge(VARCHAR,VARCHAR) FROM PUBLIC;

        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='beta10d_app_runtime') THEN
            GRANT SELECT,INSERT,UPDATE ON ai_memory_legal_holds,ai_memory_deletion_jobs,
              ai_memory_deletion_proofs TO beta10d_app_runtime;
            GRANT EXECUTE ON FUNCTION ai_memory_purge(VARCHAR,VARCHAR) TO beta10d_app_runtime;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        REVOKE ALL ON FUNCTION ai_memory_purge(VARCHAR,VARCHAR) FROM PUBLIC;
        DROP FUNCTION IF EXISTS ai_memory_purge(VARCHAR,VARCHAR);
        DROP TABLE ai_memory_deletion_proofs;
        DROP TABLE ai_memory_deletion_jobs;
        DROP TABLE ai_memory_legal_holds;

        ALTER TABLE ai_memory_usage ADD CONSTRAINT ai_memory_usage_memory_id_fkey
          FOREIGN KEY(memory_id) REFERENCES ai_memory_records(memory_id);
        ALTER TABLE ai_memory_usage ADD CONSTRAINT ai_memory_usage_version_id_fkey
          FOREIGN KEY(version_id) REFERENCES ai_memory_versions(version_id);
        ALTER TABLE ai_memory_outbox ADD CONSTRAINT ai_memory_outbox_memory_id_fkey
          FOREIGN KEY(memory_id) REFERENCES ai_memory_records(memory_id);
        ALTER TABLE ai_memory_admissions ADD CONSTRAINT ai_memory_admissions_memory_id_fkey
          FOREIGN KEY(memory_id) REFERENCES ai_memory_records(memory_id);
        ALTER TABLE ai_memory_state_transitions ADD CONSTRAINT ai_memory_state_transitions_memory_id_fkey
          FOREIGN KEY(memory_id) REFERENCES ai_memory_records(memory_id);

        ALTER TABLE ai_memory_outbox DROP CONSTRAINT ck_ai_memory_outbox_status;
        ALTER TABLE ai_memory_outbox ADD CONSTRAINT ck_ai_memory_outbox_status
          CHECK (status IN ('pending','processing','processed','failed'));
        ALTER TABLE ai_memory_records DROP CONSTRAINT ck_ai_memory_status;
        ALTER TABLE ai_memory_records DROP CONSTRAINT ck_ai_memory_usage_count;
        ALTER TABLE ai_memory_records DROP COLUMN delete_requested_at;
        ALTER TABLE ai_memory_records DROP COLUMN soft_deleted_at;
        ALTER TABLE ai_memory_records DROP COLUMN usage_count;
        ALTER TABLE ai_memory_records DROP COLUMN last_used_at;
        ALTER TABLE ai_memory_records ADD CONSTRAINT ck_ai_memory_status CHECK (
          status IN ('draft','pending','active','cold','archived','deleted')
        );
        """
    )

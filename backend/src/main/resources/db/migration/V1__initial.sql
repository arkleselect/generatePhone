-- Image ancestry and human labels remain separate from requested generation parameters.
CREATE TABLE asset (
 id VARCHAR(36) PRIMARY KEY, root_source_id VARCHAR(36) NOT NULL, parent_pose_id VARCHAR(36),
 role VARCHAR(16) NOT NULL, source_type VARCHAR(16) NOT NULL, filename VARCHAR(150) NOT NULL,
 width INT NOT NULL, height INT NOT NULL, file_size BIGINT NOT NULL, base_date VARCHAR(32) NOT NULL,
 pose_json TEXT NOT NULL, roi_json TEXT, review VARCHAR(16) NOT NULL DEFAULT 'PENDING',
 label VARCHAR(100), quality VARCHAR(16), rejection_reason VARCHAR(1000), task_id VARCHAR(36),
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
-- Draft batches are persisted before explicit confirmation authorizes any provider call.
CREATE TABLE batch (
 id VARCHAR(36) PRIMARY KEY, stage VARCHAR(16) NOT NULL, status VARCHAR(16) NOT NULL,
 mode VARCHAR(16) NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE image_task (
 id VARCHAR(36) PRIMARY KEY, batch_id VARCHAR(36) NOT NULL, input_id VARCHAR(36) NOT NULL,
 root_source_id VARCHAR(36) NOT NULL, status VARCHAR(16) NOT NULL, params_json TEXT NOT NULL,
 prompt TEXT NOT NULL, settings_json TEXT NOT NULL, attempts INT NOT NULL DEFAULT 0,
 error VARCHAR(1000), provider_request_id VARCHAR(150), output_id VARCHAR(36),
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY (batch_id) REFERENCES batch(id), FOREIGN KEY (input_id) REFERENCES asset(id)
);
CREATE INDEX task_queue ON image_task(status, created_at);
CREATE INDEX asset_review ON asset(role, review);

-- Explicit order preserves date-by-date coverage when timestamps tie.
ALTER TABLE image_task ADD COLUMN sequence_no INT NOT NULL DEFAULT 0;
CREATE INDEX task_queue_order ON image_task(batch_id, status, sequence_no);

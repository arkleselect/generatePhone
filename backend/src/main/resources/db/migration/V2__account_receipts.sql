-- Actual model information is user/tool supplied; unverified metadata is never fabricated.
ALTER TABLE image_task ADD COLUMN actual_model VARCHAR(150);
ALTER TABLE image_task ADD COLUMN execution_channel VARCHAR(40);

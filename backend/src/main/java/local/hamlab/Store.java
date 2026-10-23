package local.hamlab;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;
import java.util.List;
import java.util.Map;
import static local.hamlab.Models.*;

/** Only persistence mapping layer; services reuse these queries and typed row mappings. */
@Repository
public class Store {
    final JdbcTemplate db;
    final Json json;
    final RowMapper<Asset> assets;
    final RowMapper<Task> tasks;
    public Store(JdbcTemplate db, Json json) {
        this.db = db; this.json = json;
        assets = (r, n) -> new Asset(r.getString("id"), r.getString("root_source_id"), r.getString("parent_pose_id"),
            r.getString("role"), r.getString("source_type"), r.getString("filename"), r.getInt("width"), r.getInt("height"),
            r.getLong("file_size"), r.getString("base_date"), json.read(r.getString("pose_json"), Pose.class),
            r.getString("roi_json") == null ? null : json.read(r.getString("roi_json"), Roi.class),
            r.getString("annotations_json") == null ? List.of() : List.of(json.read(r.getString("annotations_json"), Annotation[].class)),
            r.getString("review"), r.getString("label"), r.getString("quality"), r.getString("rejection_reason"),
            r.getString("task_id"), r.getTimestamp("created_at").toInstant());
        tasks = (r, n) -> new Task(r.getString("id"), r.getString("batch_id"), r.getString("input_id"),
            r.getString("root_source_id"), r.getString("status"), json.read(r.getString("params_json"), Params.class),
            r.getString("prompt"), json.read(r.getString("settings_json"), Settings.class), r.getInt("attempts"),
            r.getString("error"), r.getString("provider_request_id"), r.getString("output_id"), r.getTimestamp("created_at").toInstant(), r.getString("actual_model"), r.getString("execution_channel"));
    }
    // Access through methods so Spring repository proxies never expose uninitialized proxy fields.
    public JdbcTemplate jdbc() { return db; }
    public Json json() { return json; }
    public RowMapper<Task> taskMapper() { return tasks; }
    public Asset asset(String id) {
        return db.query("SELECT * FROM asset WHERE id=?", assets, id).stream().findFirst()
            .orElseThrow(() -> new IllegalArgumentException("图片不存在"));
    }
    public Task task(String id) {
        return db.query("SELECT * FROM image_task WHERE id=?", tasks, id).stream().findFirst()
            .orElseThrow(() -> new IllegalArgumentException("任务不存在"));
    }
    public List<Asset> assets() { return db.query("SELECT * FROM asset ORDER BY created_at DESC, id", assets); }
    public List<Task> tasks(String batch) { return db.query("SELECT * FROM image_task WHERE batch_id=? ORDER BY sequence_no,created_at,id", tasks, batch); }
    public List<Map<String, Object>> batches() {
        return db.queryForList("SELECT id, stage, status, mode, created_at FROM batch ORDER BY created_at DESC");
    }
    public Map<String, Object> batch(String id) {
        return db.queryForList("SELECT * FROM batch WHERE id=?", id).stream().findFirst()
            .orElseThrow(() -> new IllegalArgumentException("批次不存在"));
    }
}

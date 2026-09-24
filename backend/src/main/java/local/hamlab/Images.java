package local.hamlab;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.slf4j.LoggerFactory;
import javax.imageio.ImageIO;
import javax.imageio.ImageReader;
import java.awt.*;
import java.awt.image.BufferedImage;
import java.io.*;
import java.nio.file.*;
import java.util.UUID;
import static local.hamlab.Models.*;
import static local.hamlab.Prompts.require;

/** Preserves received image bytes; creates independent thumbnails and transport masks. */
@Service
public class Images {
    private final Path root;
    private final Store store;
    public Images(@Value("${app.storage}") String storage, Store store) throws IOException {
        this.root = Path.of(storage).toAbsolutePath().normalize(); this.store = store;
        Files.createDirectories(root.resolve("images")); Files.createDirectories(root.resolve("thumbs"));
    }
    public Path root() { return root; }
    public Path file(Asset asset, boolean thumbnail) {
        return root.resolve(thumbnail ? "thumbs" : "images").resolve(thumbnail ? asset.id()+".jpg" : asset.filename());
    }
    public Asset upload(byte[] bytes, String role, String date) throws IOException {
        require(role.equals("SOURCE") || role.equals("POSE"), "上传只能为原始图或真实底图"); Prompts.date(date);
        String id = UUID.randomUUID().toString();
        return save(id, bytes, id, null, role, "REAL", date, new Pose("original",0,0,"真实上传"), null);
    }
    /** Lock the source against new task references; preserve all existing provenance. */
    @Transactional
    public void deleteSource(String id) { deleteUnreferenced(id, false); }
    /** Bulk removal is atomic: one referenced image preserves the entire selection. */
    @Transactional
    public void deleteAssets(java.util.List<String> ids) {
        require(ids!=null && !ids.isEmpty() && ids.size()<=200,"请选择1至200张图片");
        require(ids.stream().allMatch(java.util.Objects::nonNull) && new java.util.HashSet<>(ids).size()==ids.size(),"图片编号无效或重复");
        for(String id:ids.stream().sorted().toList()) deleteUnreferenced(id, true);
    }
    private void deleteUnreferenced(String id, boolean allowPose) {
        var locked = store.jdbc().queryForList("SELECT id FROM asset WHERE id=? FOR UPDATE", String.class, id);
        require(!locked.isEmpty(), "图片不存在或已删除");
        Asset asset = store.asset(id);
        require(asset.role().equals("SOURCE") || (allowPose && asset.role().equals("POSE")), "仅支持删除原始参考图或未使用底图");
        Integer tasks = store.jdbc().queryForObject(
            "SELECT COUNT(*) FROM image_task WHERE input_id=? OR root_source_id=? OR output_id=?", Integer.class, id, id, id);
        Integer children = store.jdbc().queryForObject(
            "SELECT COUNT(*) FROM asset WHERE id<>? AND (root_source_id=? OR parent_pose_id=?)", Integer.class, id, id, id);
        require(tasks == 0 && children == 0, "图片 "+id.substring(0,8)+" 已被任务或生成图片引用，不能删除；需保留原图用于追溯");
        store.jdbc().update("DELETE FROM asset WHERE id=?", id);
        // Never remove bytes before commit: rollback must leave the original usable.
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override public void afterCommit() {
                for (Path path : new Path[]{file(asset, false), file(asset, true)}) {
                    try { Files.deleteIfExists(path); }
                    catch (IOException error) {
                        // A cleanup failure leaves an inaccessible orphan, not a broken live asset.
                        LoggerFactory.getLogger(Images.class).error("Deleted asset {}: file cleanup failed for {}", id, path, error);
                    }
                }
            }
        });
    }
    public Asset generated(byte[] bytes, Task task, String stage, String mode) throws IOException {
        return save(UUID.randomUUID().toString(), bytes, task.rootSourceId(), stage.equals("DEFECT") ? task.inputId() : null,
            stage.equals("POSE") ? "POSE" : "RESULT", mode.equals("TEST") ? "TEST" : "AI", task.params().baseDate(), task.params().pose(), task.id());
    }
    private Asset save(String id, byte[] bytes, String rootId, String parent, String role, String source,
                       String date, Pose pose, String task) throws IOException {
        require(bytes.length > 0 && bytes.length <= 50*1024*1024, "图片文件为空或超过50MB");
        // Inspect dimensions before decoding to limit decompression memory consumption.
        BufferedImage image; String extension;
        try (var input = ImageIO.createImageInputStream(new ByteArrayInputStream(bytes))) {
            var readers = ImageIO.getImageReaders(input); require(readers.hasNext(), "仅支持真实 JPG、JPEG、PNG 图片");
            ImageReader reader = readers.next();
            try {
                reader.setInput(input); String format = reader.getFormatName().toLowerCase();
                require(format.equals("jpeg") || format.equals("png"), "仅支持 JPG、JPEG、PNG");
                long pixels = (long) reader.getWidth(0)*reader.getHeight(0);
                require(pixels <= 24_000_000 && pixels > 0, "图片最多2400万像素");
                image = reader.read(0); extension = format.equals("jpeg") ? ".jpg" : ".png";
            } finally { reader.dispose(); }
        }
        String filename = id+extension;
        Path original = root.resolve("images").resolve(filename), thumb = root.resolve("thumbs").resolve(id+".jpg");
        try {
            Files.write(original, bytes, StandardOpenOption.CREATE_NEW);
            double scale = Math.min(1, 480.0/Math.max(image.getWidth(),image.getHeight()));
            BufferedImage small = new BufferedImage(Math.max(1,(int)(image.getWidth()*scale)),Math.max(1,(int)(image.getHeight()*scale)),BufferedImage.TYPE_INT_RGB);
            Graphics2D g = small.createGraphics();
            g.setColor(Color.WHITE); g.fillRect(0,0,small.getWidth(),small.getHeight());
            g.setRenderingHint(RenderingHints.KEY_INTERPOLATION,RenderingHints.VALUE_INTERPOLATION_BILINEAR);
            g.drawImage(image,0,0,small.getWidth(),small.getHeight(),null); g.dispose();
            ImageIO.write(small,"jpg",thumb.toFile());
            store.jdbc().update("INSERT INTO asset(id,root_source_id,parent_pose_id,role,source_type,filename,width,height,file_size,base_date,pose_json,task_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                id,rootId,parent,role,source,filename,image.getWidth(),image.getHeight(),bytes.length,date,store.json().write(pose),task);
            return store.asset(id);
        } catch (Exception e) {
            Files.deleteIfExists(original); Files.deleteIfExists(thumb); throw e;
        }
    }
    /** The transparent rectangle is an editing hint, never a verified segmentation label. */
    public byte[] mask(Asset input, Roi roi) throws IOException {
        Prompts.roi(roi);
        BufferedImage mask = new BufferedImage(input.width(),input.height(),BufferedImage.TYPE_INT_ARGB);
        Graphics2D g = mask.createGraphics(); g.setColor(Color.WHITE); g.fillRect(0,0,input.width(),input.height());
        g.setComposite(AlphaComposite.Clear);
        g.fillRect((int)(roi.x()*input.width()),(int)(roi.y()*input.height()),Math.max(1,(int)Math.ceil(roi.width()*input.width())),Math.max(1,(int)Math.ceil(roi.height()*input.height())));
        g.dispose(); return png(mask);
    }
    /** Convert only the upload payload to PNG so reference and mask formats match; originals stay intact. */
    public byte[] transportPng(Asset input) throws IOException { return png(ImageIO.read(file(input,false).toFile())); }
    public byte[] testImage(Asset input) throws IOException {
        BufferedImage image = ImageIO.read(file(input,false).toFile());
        Graphics2D g = image.createGraphics(); int size = Math.max(12,image.getWidth()/30);
        g.setColor(new Color(160,35,35,225)); g.fillRect(0,0,image.getWidth(),size*3);
        g.setColor(Color.WHITE); g.setFont(new Font(Font.SANS_SERIF,Font.BOLD,size));
        g.drawString("TEST ONLY - NO AI GENERATION",8,size*2); g.dispose(); return png(image);
    }
    private byte[] png(BufferedImage image) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream(); ImageIO.write(image,"png",out); return out.toByteArray();
    }
    public Asset region(String id, Roi roi) {
        require(store.asset(id).role().equals("POSE"), "只有姿势底图可以框选日期区域"); Prompts.roi(roi);
        store.jdbc().update("UPDATE asset SET roi_json=? WHERE id=?",store.json().write(roi),id); return store.asset(id);
    }
    /** Passing review confirms the requested sample, while OK/NG is a separate quality judgment. */
    public Asset review(String id, Review review) {
        Asset asset = store.asset(id);
        require(!asset.role().equals("SOURCE"), "原始参考图无需审核");
        require(java.util.Set.of("PENDING","APPROVED","REJECTED").contains(review.status()), "审核状态无效");
        require(review.reason() != null && review.reason().length() <= 1000, "审核原因过长");
        if (review.status().equals("APPROVED")) {
            require(review.label() != null && !review.label().isBlank() && review.label().length() <= 100, "请填写人工确认标签");
            require(java.util.Set.of("OK","NG").contains(review.quality()), "请选择产品质量判定");
            require(!asset.role().equals("POSE") || (review.label().equals("normal") && review.quality().equals("OK")), "底图必须确认为 normal / OK");
        }
        if (review.status().equals("REJECTED")) require(!review.reason().isBlank(), "请填写不通过原因");
        store.jdbc().update("UPDATE asset SET review=?,label=?,quality=?,rejection_reason=? WHERE id=?",review.status(),
            review.status().equals("APPROVED") ? review.label() : null,review.status().equals("APPROVED") ? review.quality() : null,review.reason(),id);
        return store.asset(id);
    }
}

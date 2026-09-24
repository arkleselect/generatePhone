package local.hamlab;

import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.*;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.*;
import static local.hamlab.Models.*;

/** Thin local HTTP endpoints; all workflow constraints are enforced in backend services. */
@RestController
@RequestMapping("/api")
public class Api {
    private final DatasetPlans plans;
    private final BrowserRunner browser;
    private final Store store; private final Images images; private final Batches batches;
    private final ProviderConfig config; private final Prompts prompts; private final Exports exports; private final AccountTasks account;
    public Api(Store store,Images images,Batches batches,ProviderConfig config,Prompts prompts,Exports exports,AccountTasks account,DatasetPlans plans,BrowserRunner browser) {
        this.browser=browser;this.plans=plans;this.store=store;this.images=images;this.batches=batches;this.config=config;this.prompts=prompts;this.exports=exports;this.account=account;
    }
    @GetMapping("/health") public Map<String,String> health() { store.jdbc().queryForObject("SELECT 1",Integer.class);return Map.of("status","UP"); }
    @GetMapping("/assets") public List<Asset> assets() { return store.assets(); }
    @PostMapping("/assets") public Asset upload(@RequestParam MultipartFile file,@RequestParam String role,@RequestParam String baseDate) throws IOException {
        return images.upload(file.getBytes(),role,baseDate);
    }
    // Service enforces role and reference checks even for direct HTTP callers.
    @DeleteMapping("/assets/{id}") public void deleteSource(@PathVariable String id) { images.deleteSource(id); }
    @GetMapping("/assets/{id}/file") public ResponseEntity<FileSystemResource> file(@PathVariable String id,@RequestParam(defaultValue="false") boolean thumbnail) {
        Asset a=store.asset(id);
        return ResponseEntity.ok().header("X-Content-Type-Options","nosniff").contentType(thumbnail || a.filename().endsWith(".jpg") ? MediaType.IMAGE_JPEG : MediaType.IMAGE_PNG)
            .body(new FileSystemResource(images.file(a,thumbnail)));
    }
    @PutMapping("/assets/{id}/roi") public Asset roi(@PathVariable String id,@RequestBody Roi roi) { return images.region(id,roi); }
    @PutMapping("/assets/{id}/review") public Asset review(@PathVariable String id,@RequestBody Review review) { return images.review(id,review); }
    @GetMapping("/date-positions") public List<Map<String,Object>> positions(@RequestParam String date) { return prompts.mapping(date); }
    @GetMapping("/browser/status") public Map<?,?> browserStatus() { return browser.status(); }
    @PostMapping("/browser/{action}") public Map<?,?> browserAction(@PathVariable String action) throws Exception { return browser.action(action); }
    @PostMapping("/browser/callback") public Map<?,?> browserCallback(@RequestBody Map<String,String> body) throws Exception { return browser.callback(body.get("url")); }
    @GetMapping("/defects") public Map<String,DefectCatalog.Definition> defects() { return DefectCatalog.ALL; }
    @GetMapping("/config") public Map<String,Object> config() { return Map.of("settings",config.settings(),"executionMode","ACCOUNT","maskSupported",false,"seedSupported",false); }
    @PutMapping("/config") public void configure(@RequestBody Settings settings) throws IOException { config.save(settings); }
    @GetMapping("/batches") public List<Map<String,Object>> batches() { return store.batches(); }
    @GetMapping("/batches/{id}") public Map<String,Object> detail(@PathVariable String id) { return batches.detail(id); }
    @GetMapping("/tasks/{id}") public Task task(@PathVariable String id) { return store.task(id); }
    @GetMapping("/tasks") public List<Task> tasks() { return store.jdbc().query("SELECT * FROM image_task ORDER BY created_at DESC",store.taskMapper()); }
    // Share expansion with draft creation so the displayed quantity matches persisted work.
    @PostMapping("/plans/estimate") public Map<String,Object> estimate(@RequestBody Draft draft) {
        int perInput=plans.expand(draft).size();
        int total=perInput*(draft.inputIds()==null?0:draft.inputIds().size());
        return Map.of("total",total,"perInput",perInput,"limit",DatasetPlans.LIMIT);
    }
    @PostMapping("/assets/delete") public void deleteAssets(@RequestBody List<String> ids) { images.deleteAssets(ids); }
    @PostMapping("/batches") public Map<String,Object> draft(@RequestBody Draft draft) { return batches.draft(draft); }
    @DeleteMapping("/batches/{id}") public void deleteBatch(@PathVariable String id) { batches.delete(id); }
    @PutMapping("/batches/{id}/review") public void reviewBatch(@PathVariable String id,@RequestBody BatchReview body) { images.reviewBatch(id,body); }
    @PostMapping("/batches/{id}/confirm") public void confirm(@PathVariable String id,@RequestBody Confirm confirm) { batches.confirm(id,confirm); }
    @PostMapping("/batches/{id}/{action}") public void action(@PathVariable String id,@PathVariable String action) { batches.action(id,action); }
    @PostMapping("/tasks/{id}/resolve") public void resolve(@PathVariable String id,@RequestBody Map<String,Boolean> body) { batches.resolveUnknown(id,Boolean.TRUE.equals(body.get("verifiedNotAccepted"))); }
    @PostMapping("/tasks/{id}/regenerate") public Map<String,Object> regenerate(@PathVariable String id) { return batches.regenerate(id); }
    // Account cooperation exposes only confirmed work, never account cookies or tokens.
    @GetMapping("/account/next") public Map<String,Object> nextAccountTask() { return account.next(); }
    @PostMapping("/tasks/{id}/result") public Asset accountResult(@PathVariable String id,@RequestParam MultipartFile file,
        @RequestParam(defaultValue="") String actualModel,@RequestParam(defaultValue="MANUAL_CHATGPT") String channel) throws IOException {
        return account.complete(id,file.getBytes(),actualModel,channel);
    }
    @PostMapping("/tasks/{id}/failure") public void accountFailure(@PathVariable String id,@RequestBody Map<String,Object> body) {
        account.fail(id,Objects.toString(body.get("reason"),""),Boolean.TRUE.equals(body.get("uncertain")));
    }
    @GetMapping("/tasks/{id}/bundle") public void bundle(@PathVariable String id,HttpServletResponse response) throws IOException {
        store.task(id); response.setContentType("application/zip");response.setHeader("Content-Disposition","attachment; filename=account-task.zip");
        account.bundle(id,response.getOutputStream());
    }
    @GetMapping("/export") public void export(@RequestParam(defaultValue="") String pose,@RequestParam(defaultValue="") String defect,
        @RequestParam(defaultValue="APPROVED") String review,@RequestParam(defaultValue="") String batch,HttpServletResponse response) throws IOException {
        var selected=exports.select(pose,defect,review);
        if(!batch.isBlank()) selected=selected.stream().filter(a->store.task(a.taskId()).batchId().equals(batch)).toList();
        Prompts.require(!selected.isEmpty(),"没有符合筛选条件的真实生成结果；测试图片不导出");
        response.setContentType("application/zip");response.setHeader("Content-Disposition","attachment; filename=hamlab-dataset.zip");
        exports.zip(response.getOutputStream(),selected);
    }
}

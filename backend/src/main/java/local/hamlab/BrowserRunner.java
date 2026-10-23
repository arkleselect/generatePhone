package local.hamlab;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import jakarta.annotation.PreDestroy;
import java.net.URI;
import java.net.http.*;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;
import static local.hamlab.Prompts.require;

/** Owns a local browser worker; credentials stay in its private browser directory. */
@Service
public class BrowserRunner {
    private final Path directory, state;
    private final String python, apiUrl;
    private final Json json;
    private final HttpClient client=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build();
    private final String token=UUID.randomUUID()+""+UUID.randomUUID();
    private Process process;
    public BrowserRunner(@Value("${app.browser-directory:./automation}") String directory,
                         @Value("${app.storage:./data}") String storage,
                         @Value("${app.browser-python:./automation/.venv/bin/python}") String python,
                         @Value("${server.port:8080}") int port,Json json) {
        this.directory=Path.of(directory).toAbsolutePath().normalize(); this.state=Path.of(storage).toAbsolutePath().resolve("browser");
        this.python=Path.of(python).toAbsolutePath().normalize().toString(); this.apiUrl="http://127.0.0.1:"+port+"/api"; this.json=json;
    }
    /** Status reads never launch a browser or begin generation. */
    public synchronized Map<?,?> status() {
        if(process==null || !process.isAlive()) return Map.of("phase","STOPPED","enabled",false,"message","浏览器执行器未启动");
        try { return request("status","GET"); }
        catch(Exception e) { return Map.of("phase","STARTING","enabled",false,"message","正在启动本地执行器"); }
    }
    /** Only explicit login/start commands launch the worker; start still requires confirmed tasks. */
    public synchronized Map<?,?> action(String action) throws Exception {
        require(Set.of("login","start","pause").contains(action),"浏览器操作无效");
        if(process==null || !process.isAlive()) {
            require(!action.equals("pause"),"执行器尚未启动");
            require(Files.isExecutable(Path.of(python)),"请先按 automation/README.md 安装 Python 虚拟环境");
            Files.createDirectories(state);
            ProcessBuilder builder=new ProcessBuilder(python,"main.py","serve","--port","8091").directory(directory.toFile());
            builder.environment().put("HAMLAB_API_URL",apiUrl);
            builder.environment().put("BROWSER_STATE_DIR",state.toString());
            builder.environment().put("CONTROL_TOKEN",token);
            builder.environment().put("HAMLAB_OWNER_PID",Long.toString(ProcessHandle.current().pid()));
            builder.redirectErrorStream(true).redirectOutput(ProcessBuilder.Redirect.appendTo(state.resolve("worker.log").toFile()));
            process=builder.start();
            for(int i=0;i<100;i++) {
                if(!process.isAlive()) throw new IllegalArgumentException("执行器启动失败，请检查 8091 端口和 data/browser/worker.log");
                try { request("status","GET"); break; } catch(Exception ignored) { Thread.sleep(100); }
            }
        }
        return request(action,"POST");
    }
    private Map<?,?> request(String action,String method) throws Exception {
        return request(action,method,"");
    }
    public synchronized Map<?,?> callback(String url) throws Exception {
        require(process!=null && process.isAlive(),"请先点击登录 / 连接账号");
        require(url!=null && url.length()<=16000,"回调网址无效");
        return request("callback","POST",json.write(Map.of("url",url)));
    }
    private Map<?,?> request(String action,String method,String payload) throws Exception {
        var request=HttpRequest.newBuilder(URI.create("http://127.0.0.1:8091/"+action)).timeout(Duration.ofSeconds(40))
            .header("X-Worker-Token",token).header("Content-Type","application/json")
            .method(method,HttpRequest.BodyPublishers.ofString(payload)).build();
        var response=client.send(request,HttpResponse.BodyHandlers.ofString());
        Map<?,?> body=json.read(response.body(),Map.class);
        require(response.statusCode()==200,Objects.toString(body.get("message"),"浏览器执行器不可用")); return body;
    }
    /** Stop the owned child only; its persisted receipts prevent duplicate submissions after restart. */
    @PreDestroy public synchronized void close() { if(process!=null) process.destroy(); }
}

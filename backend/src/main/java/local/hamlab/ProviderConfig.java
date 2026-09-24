package local.hamlab;

import org.springframework.stereotype.Service;
import java.nio.file.*;
import java.io.IOException;
import java.util.Set;
import static local.hamlab.Models.*;
import static local.hamlab.Prompts.require;

/** Account cooperation preferences contain no session cookies, credentials or API keys. */
@Service
public class ProviderConfig {
    private final Path path;
    private final Json json;
    private volatile Settings settings;
    public ProviderConfig(Images images, Json json) throws IOException {
        this.path=images.root().resolve("account-settings.json"); this.json=json;
        settings=Files.exists(path) ? json.read(Files.readString(path),Settings.class) :
            new Settings("CHATGPT_ACCOUNT","https://chatgpt.com","Image 2.5（期望模型，需在账号界面确认）","保持参考图比例","账号默认",0);
        validate(settings);
    }
    public Settings settings() { return settings; }
    public synchronized void save(Settings value) throws IOException {
        validate(value); Path temp=Files.createTempFile(path.getParent(),"account-",".tmp");
        try { Files.writeString(temp,json.write(value)); Files.move(temp,path,StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE); settings=value; }
        finally { Files.deleteIfExists(temp); }
    }
    private void validate(Settings s) {
        require(s!=null && "CHATGPT_ACCOUNT".equals(s.provider()) && "https://chatgpt.com".equals(s.baseUrl()),"仅使用 ChatGPT 账号协作模式");
        require(s.model()!=null && !s.model().isBlank() && s.model().length()<=120,"请填写期望模型，实际模型以账号界面为准");
        require(Set.of("保持参考图比例","横向照片","竖向照片","正方形照片").contains(s.size()),"画幅偏好无效");
        require("账号默认".equals(s.quality()) && s.timeoutSeconds()==0,"账号模式不支持 API 质量或超时参数");
    }
}

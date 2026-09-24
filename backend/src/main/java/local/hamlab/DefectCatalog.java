package local.hamlab;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.core.io.ClassPathResource;
import java.util.*;
import java.util.stream.Collectors;

/** One shared catalog supplies Python templates, Java validation and Vue labels. */
public final class DefectCatalog {
    public record Definition(String label,String datasetType,boolean positions,boolean severity,String effect) {}
    public static final Map<String,Definition> ALL = load();
    private DefectCatalog() {}
    private static Map<String,Definition> load() {
        try(var input = new ClassPathResource("catalog/defects.json").getInputStream()) {
            Map<String,Definition> entries = new ObjectMapper().readValue(input,new TypeReference<LinkedHashMap<String,Definition>>(){});
            return Collections.unmodifiableMap(entries);
        } catch(Exception error) { throw new IllegalStateException("缺陷配置读取失败",error); }
    }
    public static Set<String> positionTypes() { return ALL.entrySet().stream().filter(e->e.getValue().positions()).map(Map.Entry::getKey).collect(Collectors.toUnmodifiableSet()); }
    public static Set<String> severityTypes() { return ALL.entrySet().stream().filter(e->e.getValue().severity()).map(Map.Entry::getKey).collect(Collectors.toUnmodifiableSet()); }
}

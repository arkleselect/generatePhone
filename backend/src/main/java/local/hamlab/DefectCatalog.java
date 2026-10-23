package local.hamlab;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.core.io.ClassPathResource;
import java.util.*;
import java.util.stream.Collectors;

/** One shared catalog supplies Python templates, Java validation and Vue labels. */
public final class DefectCatalog {
    /** scope: date edits the framed date region, casing edits casing locally, shape may deform the whole product. */
    public record Definition(String label,String datasetType,boolean positions,boolean severity,String effect,String scope,List<String> variants) {
        public Definition {
            scope=scope==null?"date":scope; variants=variants==null?List.of():List.copyOf(variants);
            if(!Set.of("date","casing","shape").contains(scope)) throw new IllegalStateException("缺陷范围配置无效："+scope);
        }
        public boolean dateScoped() { return "date".equals(scope); }
    }
    public static final Map<String,Definition> ALL = load();
    private DefectCatalog() {}
    private static Map<String,Definition> load() {
        try(var input = new ClassPathResource("catalog/defects.json").getInputStream()) {
            Map<String,Definition> entries = new ObjectMapper().readValue(input,new TypeReference<LinkedHashMap<String,Definition>>(){});
            return Collections.unmodifiableMap(entries);
        } catch(Exception error) { throw new IllegalStateException("缺陷配置读取失败",error); }
    }
    public static Set<String> positionTypes() { return ALL.entrySet().stream().filter(e->e.getValue().positions()).map(Map.Entry::getKey).collect(Collectors.toUnmodifiableSet()); }
    /** Only date-scoped defects need the framed date region and its edit mask. */
    public static boolean dateScoped(String type) { var d=ALL.get(type); return d==null || d.dateScoped(); }
    public static Set<String> severityTypes() { return ALL.entrySet().stream().filter(e->e.getValue().severity()).map(Map.Entry::getKey).collect(Collectors.toUnmodifiableSet()); }
}

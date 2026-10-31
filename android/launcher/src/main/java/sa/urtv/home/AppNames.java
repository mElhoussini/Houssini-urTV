package sa.urtv.home;

import android.content.Context;
import android.content.pm.ResolveInfo;

import java.util.HashMap;
import java.util.Map;

/**
 * The name shown for an app: the one the owner's agent gave it on this TV (optimize/dock.sh name), else the English
 * name from res/values/app_names.xml, else its own.
 */
final class AppNames {
    static final int MAX_LEN = 30;
    private static Map<String, String> table;   // package -> preferred English name, read once

    private AppNames() {}

    static String label(Context c, ResolveInfo ri) {
        return label(c, ri, given(c));
    }

    static String label(Context c, ResolveInfo ri, Map<String, String> given) {
        String set = given.get(ri.activityInfo.packageName);
        if (set != null) return set;
        String preferred = table(c).get(ri.activityInfo.packageName);
        if (preferred != null) return preferred;
        return String.valueOf(ri.loadLabel(c.getPackageManager()));
    }

    /** Where the shown name comes from, for dock.sh names: agent, own, table. */
    static String source(Context c, ResolveInfo ri, Map<String, String> given) {
        if (given.containsKey(ri.activityInfo.packageName)) return "agent";
        return table(c).containsKey(ri.activityInfo.packageName) ? "table" : "own";
    }

    /** Names set on this TV, kept as "pkg|name" lines in the home screen's preferences. */
    static Map<String, String> given(Context c) {
        Map<String, String> m = new HashMap<>();
        for (String row : Dock.prefs(c).getString("names", "").split("\n")) {
            int bar = row.indexOf('|');
            if (bar > 0) m.put(row.substring(0, bar), row.substring(bar + 1));
        }
        return m;
    }

    static void save(Context c, Map<String, String> m) {
        StringBuilder b = new StringBuilder();
        for (Map.Entry<String, String> e : m.entrySet()) b.append(e.getKey()).append('|').append(e.getValue()).append('\n');
        Dock.prefs(c).edit().putString("names", b.toString()).apply();
    }

    /** A name the agent may set: one line, at most MAX_LEN characters, no separators or control characters. */
    static boolean valid(String name) {
        if (name.isEmpty() || name.length() > MAX_LEN || name.indexOf('|') >= 0 || name.indexOf(';') >= 0) return false;
        for (int i = 0; i < name.length(); i++) {
            if (Character.isISOControl(name.charAt(i))) return false;
        }
        return true;
    }

    private static synchronized Map<String, String> table(Context c) {
        if (table == null) {
            Map<String, String> t = new HashMap<>();
            for (String row : c.getApplicationContext().getResources().getStringArray(R.array.app_names)) {
                int bar = row.indexOf('|');
                if (bar > 0) t.put(row.substring(0, bar).trim(), row.substring(bar + 1).trim());
            }
            table = t;
        }
        return table;
    }
}

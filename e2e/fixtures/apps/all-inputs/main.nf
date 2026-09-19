// E2E fixture: writes every received param to outdir/params-received.json, plus a
// description of the files behind file/folder/writeFile params, so tests can assert on them.
params.outdir = 'results'

def describePath(Object value) {
    if (value == null || value.toString().isEmpty()) {
        return null
    }
    def f = new File(value.toString())
    if (!f.exists()) {
        return [path: value.toString(), exists: false]
    }
    if (f.isDirectory()) {
        def names = (f.listFiles() ?: []).collect { it.name }.sort()
        return [path: value.toString(), exists: true, type: 'folder', files: names]
    }
    return [path: value.toString(), exists: true, type: 'file', name: f.name, size: f.length(), content: (f.length() < 4096 ? f.text : null)]
}

process ECHO_PARAMS {
    publishDir params.outdir, mode: 'copy'

    input:
    val received

    output:
    path 'params-received.json'
    path 'files-received.json'

    exec:
    def files = [:]
    ['data_file', 'data_folder', 'notes', 'local_file', 'local_folder'].each { key ->
        files[key] = describePath(received[key])
    }
    task.workDir.resolve('params-received.json').text = groovy.json.JsonOutput.prettyPrint(groovy.json.JsonOutput.toJson(received))
    task.workDir.resolve('files-received.json').text = groovy.json.JsonOutput.prettyPrint(groovy.json.JsonOutput.toJson(files))
}

workflow {
    def received = new LinkedHashMap(params)
    println "::message:: Received ${received.size()} params"
    ECHO_PARAMS(channel.of(received))
}

// E2E fixture (Taxodactyl-shaped): publish run.log and result.txt into outdir.
params.outdir = 'results'
params.who = ''
params.sleep_seconds = ''

process WRITE {
    publishDir params.outdir, mode: 'copy'

    input:
    val who

    output:
    path 'run.log'
    path 'result.txt'

    exec:
    task.workDir.resolve('run.log').text =
        '2026-01-01 - INFO - starting\n' +
        '2026-01-01 - DEBUG - Vault: key-b\n' +
        '2026-01-01 - DEBUG - Vault: key-a\n' +
        '2026-01-01 - DEBUG - Vault: key-a\n'
    task.workDir.resolve('result.txt').text = "analyst=${who}\n"
}

workflow {
    println "::message:: Pipeline step ran for ${params.who}"
    WRITE(channel.of(params.who))
}

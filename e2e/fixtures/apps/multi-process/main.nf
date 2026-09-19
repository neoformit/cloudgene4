// E2E fixture: 3 chained processes x 5 tasks, each task sleeps ~1 s (progress rendering).
params.tasks = 5
params.outdir = 'results'

process ALIGN {
    input:
    val i

    output:
    val i

    script:
    """
    sleep 1
    """
}

process CALL {
    input:
    val i

    output:
    val i

    script:
    """
    sleep 1
    """
}

process REPORT {
    publishDir params.outdir, mode: 'copy'

    input:
    val i

    output:
    path "report_${i}.txt"

    script:
    """
    sleep 1
    echo "chunk ${i}" > report_${i}.txt
    """
}

workflow {
    println "::message:: Processing ${params.tasks} chunks in 3 stages"
    REPORT(CALL(ALIGN(channel.of(1..(params.tasks as int)))))
}

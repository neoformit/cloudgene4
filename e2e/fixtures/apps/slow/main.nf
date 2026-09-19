// E2E fixture: sleeps for params.seconds (cancel / queue tests).
params.seconds = 60
params.outdir = 'results'

process SLEEP {
    publishDir params.outdir, mode: 'copy'

    input:
    val secs

    output:
    path 'slept.txt'

    script:
    """
    sleep ${secs as int}
    echo "slept ${secs as int}" > slept.txt
    """
}

workflow {
    println "::message:: Sleeping for ${params.seconds} seconds"
    SLEEP(channel.of(params.seconds))
}

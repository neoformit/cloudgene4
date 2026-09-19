// E2E fixture: always fails after emitting an ::error:: annotation.
params.outdir = 'results'

process FAIL {
    script:
    """
    echo "::error::Intentional failure"
    exit 1
    """
}

workflow {
    println "::error::Intentional failure"
    FAIL()
}

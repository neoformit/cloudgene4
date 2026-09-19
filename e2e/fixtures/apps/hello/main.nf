// E2E fixture: write the given message into outdir/hello.txt.
// The file is written from Groovy (exec:) so quotes/unicode never pass through a shell.
params.message = 'Hello'
params.outdir = 'results'

process SAY_HELLO {
    publishDir params.outdir, mode: 'copy'

    input:
    val msg

    output:
    path 'hello.txt'

    exec:
    task.workDir.resolve('hello.txt').text = msg + '\n'
}

workflow {
    println "::message:: Hello from the hello fixture: ${params.message}"
    SAY_HELLO(channel.of(params.message))
}

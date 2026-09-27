// publishDir with the DEFAULT mode (symlink): the published file is a symlink into the work dir.
params.message = 'hello'
params.outdir = 'results'

process WRITE {
    publishDir params.outdir

    input:
    val msg

    output:
    path 'out.txt'

    exec:
    task.workDir.resolve('out.txt').text = msg + '\n'
}

workflow {
    WRITE(channel.of(params.message))
}

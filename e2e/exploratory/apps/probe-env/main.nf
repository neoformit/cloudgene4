// T07c exploratory fixture: report what config/env/profile/work dir the pipeline really got.
params.probe_global = 'unset'
params.probe_app = 'unset'
params.outdir = 'results'

workflow {
    println "::message::PARAM probe_global=${params.probe_global}"
    println "::message::PARAM probe_app=${params.probe_app}"
    println "::message::ENV PROBE_GLOBAL=${System.getenv('PROBE_GLOBAL')}"
    println "::message::ENV PROBE_APP=${System.getenv('PROBE_APP')}"
    println "::message::ENV CLOUDGENE_JOB_ID=${System.getenv('CLOUDGENE_JOB_ID')}"
    println "::message::ENV CLOUDGENE_USER_NAME=${System.getenv('CLOUDGENE_USER_NAME')}"
    println "::message::PROFILE=${workflow.profile}"
    println "::message::WORKDIR=${workflow.workDir}"
}

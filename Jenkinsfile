#!/usr/bin/env groovy
/*
 * Job URL: http://eos-jenkins.colo.seagate.com/job/Hare/job/hare-test-ci-poc/
 *
 * Pipeline syntax: https://www.jenkins.io/doc/book/pipeline/syntax/
 * Groovy syntax: http://groovy-lang.org/syntax.html
 */

pipeline {

    // Agent independent process so running on any agent wont cause problem
    agent { label 'docker-nightly-node' }

    // Pipeline timeout 1h and added timestamp to jenkins log
    options {
        timeout(time: 90, unit: 'MINUTES')
        disableConcurrentBuilds()
        timestamps()
    }

    // Build number accepted as parameter to get particular build
    // provisioner cli default - 'last_successful'
    parameters {
        string(name: 'host', defaultValue: 'ssc-vm-0581.colo.seagate.com', description: 'Machine to run tests on')
    }

    // VM information is maintained in a single location so we can
    // easily switch between multiple VM
    environment {
        VM_HOST_FQDN = "${host}"
        MANAGEIQ_TOKEN_CRED_ID="shailesh-cloudform-cred"
        VM_USER_PASS_CRED_ID="bb694996-b19f-4f1a-8686-46cc9ba7d120"
        GITHUB_TOKEN = credentials('shailesh-github-token')
    }

    // Pipeline Execution
    stages {

        // Create infrastcrure required for further pipeline execution
        stage("Prepare Test Infrastructure") {
            when { expression { true } }
            steps {
                retry(2) {
                    script {
                        withCredentials([usernameColonPassword(credentialsId: "$MANAGEIQ_TOKEN_CRED_ID", variable: 'manageiq_cred'), usernamePassword(credentialsId: "$VM_USER_PASS_CRED_ID", passwordVariable: 'pass', usernameVariable: 'user')]) {
                            // Step reverts teh snapshot to clean version
                            sh label: 'manageif_infra', returnStdout: true, script: '''
                                yum install -y sshpass
                                curl -s http://gitlab.mero.colo.seagate.com/shailesh.vaidya/scripts/raw/master/cloudform/setup.sh | bash /dev/stdin -h ${VM_HOST_FQDN} -x "${manageiq_cred}"
                            '''
                            // Step validates the VM access
                            sh label: 'test_infra', returnStdout: true, script: """
                                set -x
                                sleep 30
                                sshpass -p '${pass}' ssh -o StrictHostKeyChecking=no -q $user@$VM_HOST_FQDN exit
                                if [ \$? -ne 0 ]; then
                                    echo 'ssh command failed' >&2
                                    exit 1
                                fi
                            """
                        }
                    }
                }
            }
        }

        stage("Execute Test") {
            steps {
                script {
                    def remote = getTestMachine(VM_HOST_FQDN)

                    def commandResult = sshCommand remote: remote, command: '''
                        echo 'Test Started on Node'
                        echo '---------------------------'
                        #XXX# git clone https://$GITHUB_TOKEN@github.com/shailesh-vaidya/hare.git
                        #XXX# ls -ltr
                        #XXX# hare/ci/test-boot1
                        export
                        echo 'XXX Test completed'
                        echo "Current $(pwd)"
                        sleep 3600
                    '''
                    echo "Result: " + commandResult
                }
            }
        }
    }
}

// Method returns VM Host Information ( host, ssh cred)
def getTestMachine(String host) {
    def remote = [:]
    withCredentials([usernamePassword(credentialsId: "$VM_USER_PASS_CRED_ID", passwordVariable: 'pass', usernameVariable: 'user')]) {
        remote.name = 'eos'
        remote.host = host
        remote.user = user
        remote.password = pass
        remote.allowAnyHosts = true
        remote.fileTransfer = 'scp'
    }
    return remote
}

#!/usr/bin/env groovy
/*
 * Job URL: http://eos-jenkins.mero.colo.seagate.com/job/Hare/job/vvv.hare-multibranch
 *
 * Pipeline syntax: https://www.jenkins.io/doc/book/pipeline/syntax/
 * Groovy syntax: http://groovy-lang.org/syntax.html
 */

pipeline {
    agent { label 'docker-nightly-node' }

    options {
        timeout(90)  // abort the build after that many minutes
        disableConcurrentBuilds()
        timestamps()
        ansiColor('xterm')  // XXX Delete if not useful.

        lock('hare-ci-vm')  // get exclusive access to the SSC VM
    }

    // parameters {
    //     string(name: 'vm_host', defaultValue: 'ssc-vm-0581.colo.seagate.com', description: 'Machine to run tests on')
    // }

    environment {
        // VM_HOST = "${vm_host}"
        VM_HOST = 'ssc-vm-0581.colo.seagate.com'
        MANAGEIQ_TOKEN_CRED_ID = 'shailesh-cloudform-cred'
        VM_USER_PASS_CRED_ID = 'bb694996-b19f-4f1a-8686-46cc9ba7d120'
        // GITHUB_TOKEN = credentials('shailesh-github-token')
    }

    stages {
        stage('Build') {
            steps {
                sh(
                    label: 'XXX-DELETEME',
                    script: '''
export
''')
            }
        }

        stage('Prepare VM') {
            steps {
                retry(2) {
                    withCredentials([
                        usernameColonPassword(
                            credentialsId: "$MANAGEIQ_TOKEN_CRED_ID",
                            variable: 'manageiq_cred'),
                        usernamePassword(
                            credentialsId: "$VM_USER_PASS_CRED_ID",
                            passwordVariable: 'pass',
                            usernameVariable: 'user')]) {

                        // Reset VM to "clean" state (restore from a snapshot)
                        sh(
                            label: 'Reset VM',
                            script: '''
yum install -y sshpass
# XXX
curl -s http://gitlab.mero.colo.seagate.com/shailesh.vaidya/scripts/raw/master/cloudform/setup.sh | bash /dev/stdin -h $VM_HOST -x $manageiq_cred
''')
                        // XXX-TODO: use `sshCommand` instead
                        sh(
                            label: 'Check if VM is accessible',
                            script: '''
sleep 30  # XXX-DELETEME
sshpass -p '$pass' ssh -o StrictHostKeyChecking=no -q $user@$VM_HOST :
''')
                    }
                }
            }
        }

        stage('Test') {
            steps {
                script {
                    def remote = withCredentials([
                        usernamePassword(
                            credentialsId: "$VM_USER_PASS_CRED_ID",
                            passwordVariable: 'pass',
                            usernameVariable: 'user')]) {
                        def remote = [:]
                        remote.name = '$VM_HOST'
                        remote.host = '$VM_HOST'
                        remote.user = user
                        remote.password = pass
                        remote.allowAnyHosts = true
                        // remote.fileTransfer = 'scp'  // XXX-DELETEME
                        return remote
                    }
                    sshCommand remote: remote, command: '''
echo XXX; export
'''
                }
            }
        }
    }
}

#!/usr/bin/env groovy
/*
 * Job URL: http://eos-jenkins.mero.colo.seagate.com/job/Hare/job/hare-test-ci/
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

    environment {
        REPO_NAME = 'cortx-hare'
        VM_FQDN = 'ssc-vm-0581.colo.seagate.com'
        VM_CRED = credentials('bb694996-b19f-4f1a-8686-46cc9ba7d120')
        GITHUB_TOKEN = credentials('shailesh-github-token')
    }

    stages {
        stage('Prepare VM') {
            environment {
                SSC_AUTH = credentials('shailesh-cloudform-cred')
            }
            steps {
                sh 'VERBOSE=true jenkins/vm-reset'
            }
        }

        stage('Prepare environment') {
            parallel {
                stage('Download cortx-hare repo') {
                    steps {
                        script {
                            def remote = getTestMachine(VM_FQDN)

                            def commandResult = sshCommand remote: remote, command: """
                            rm -rf $REPO_NAME
                            mkdir $REPO_NAME
                            cd $REPO_NAME
                            git init
                            git remote add origin https://$GITHUB_TOKEN@github.com/Seagate/'$REPO_NAME'.git
                            git fetch --depth 1 origin refs/pull/$CHANGE_ID/head
                            git checkout FETCH_HEAD
                            git submodule update --init
                            git log -1
                            ls -la
                            """
                            echo "Result: " + commandResult
                        }
                    }
                }
                stage('Prepare RPM dependencies') {
                    stages {
                        stage('Prepare repo files') {
                            steps {
                                script {
                                    def remote = getTestMachine(VM_FQDN)
                                    def commandResult = sshScript remote: remote, script: "jenkins/prepare-yum-repos.sh"
                                    echo "Result: " + commandResult
                                }
                            }
                        }
                        // TODO: Revise when VM snapshot is ready
                        stage('Install Dependencies') {
                            steps {
                                script {
                                    def remote = getTestMachine(VM_FQDN)
                                    def commandResult = sshCommand remote: remote, command: """
                                    yum install cortx-motr{,-devel} -y
                                    yum install python3 python3-devel gcc rpm-build -y
                                    """
                                    echo "Result: " + commandResult
                                }
                            }
                        }
                    }
                }
            }
        }

        stage('RPM test: build & install') {
            steps {
                script {
                    def remote = getTestMachine(VM_FQDN)
                    def commandResult = sshCommand remote: remote, command: """
                        cd $REPO_NAME
                        make rpm
                        package_path=\$(find /root/rpmbuild/RPMS/x86_64/ | grep -E "cortx\\-hare\\-[0-9]+.*\\.rpm")
                        yum install -y \$package_path
                        """
                    echo "Result: " + commandResult
                }
            }
        }

        stage('Bootstrap singlenode') {
            steps {
                script {
                    def remote = getTestMachine(VM_FQDN)
                    def commandResult = sshScript remote: remote, script: "jenkins/bootstrap-singlenode.sh"
                    echo "Result: " + commandResult
                }
            }
        }

        stage('Unit-tests') {
            steps {
                script {
                    def remote = getTestMachine(VM_FQDN)
                    def commandResult = sshCommand remote: remote, command: """
                        cd $REPO_NAME
                        export PATH=/opt/seagate/cortx/hare/bin:\$PATH
                        make check
                        make test
                        #XXX
                        #make install
                        """
                    echo "Result: " + commandResult
                }
            }
        }

        stage('Stop cluster') {
            steps {
                script {
                    def remote = getTestMachine(VM_FQDN)
                    def commandResult = sshCommand remote: remote, command: """
                        PATH=/opt/seagate/cortx/hare/bin/:\$PATH
                        hctl shutdown
                        """
                    echo "Result: " + commandResult
                }
            }
        }

        stage('I/O test with m0crate') {
            steps {
                script {
                    def remote = getTestMachine(VM_FQDN)
                    // sshScript does not work in this case for unknown reason
                    def commandResult = sshCommand remote: remote, command: """
                        cd $REPO_NAME
                        ./jenkins/test-boot1.sh
                        """
                    echo "Result: " + commandResult
                }
            }
        }

        // NOTE: Add here new stages with tests if needed

    }
}

// Method returns VM Host Information ( host, ssh cred)
def getTestMachine(String host) {
    def remote = [:]
    remote.name = 'cortx-vm-name'
    remote.host = host
    remote.user =  VM_CRED_USR
    remote.password = VM_CRED_PSW
    remote.allowAnyHosts = true
    remote.fileTransfer = 'scp'

    return remote
}

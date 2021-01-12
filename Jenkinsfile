#!/usr/bin/env groovy
/*
 * Copyright (c) 2020 Seagate Technology LLC and/or its Affiliates
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 * For any questions about this software or licensing,
 * please email opensource@seagate.com or cortx-questions@seagate.com.
 */

/*
 * Pipeline syntax: https://www.jenkins.io/doc/book/pipeline/syntax/
 * Groovy syntax: http://groovy-lang.org/syntax.html
 */

pipeline {
    agent { label 'docker-cp-centos-7.8.2003-node' }

    options {
        timeout(50)  // abort the build after that many minutes
        disableConcurrentBuilds()
        timestamps()
        ansiColor('xterm')  // XXX Delete if not useful.
        lock('hare-ci-vm')  // get exclusive access to the SSC VM
    }

    environment {
        REPO_NAME = 'cortx-hare'
        VM_FQDN = 'ssc-vm-1889.colo.seagate.com' // SSC VM used for Hare CI
        VM_CRED = credentials('node-user') // To connect SSC VM over SSH
        GITHUB_TOKEN = credentials('cortx-admin-github') // To clone cortx-hare repo
    }

    stages {
        stage('Prepare VM') {
            environment {
                SSC_AUTH = credentials('RE-CF-CRED') // To connect SSC CloudForm
            }
            steps {
                sh 'VERBOSE=true jenkins/vm-reset'
            }
        }
        stage('Prepare environment') {
            parallel {
                stage('Download cortx-hare repo from static branch') {
                    when { not { changeRequest() } }
                    steps {
                        script {
                            def remote = getTestMachine(VM_FQDN)
                            def commandResult = sshCommand remote: remote, command: """
                            rm -rf $REPO_NAME
                            git clone https://$GITHUB_TOKEN@github.com/Seagate/'$REPO_NAME'.git
                            cd $REPO_NAME
                            git checkout $BRANCH_NAME
                            git log -1
                            ls -la
                            """
                            echo "Result: " + commandResult
                        }
                    }
                }
                stage('Download cortx-hare repo from pull request') {
                    when { changeRequest() }
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
                                    def commandResult = sshScript(
                                        remote: remote,
                                        script: "jenkins/prepare-yum-repos"
                                    )
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
            options {
                timeout(time: 2, unit: 'MINUTES')
            }
            steps {
                script {
                    def remote = getTestMachine(VM_FQDN)
                    def commandResult = sshScript(
                        remote: remote,
                        script: "jenkins/bootstrap-singlenode"
                    )
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
                        """
                    echo "Result: " + commandResult
                }
            }
        }

        stage('Stop cluster') {
            options {
                timeout(time: 10, unit: 'MINUTES')
            }
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
            options {
                timeout(time: 10, unit: 'MINUTES')
            }
            steps {
                script {
                    def remote = getTestMachine(VM_FQDN)
                    // sshScript does not work in this case for unknown reason
                    def commandResult = sshCommand remote: remote, command: """
                        cd $REPO_NAME
                        jenkins/test-boot1
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

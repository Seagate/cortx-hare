CENTOS_RELEASE  := latest
NAMESPACE       := registry.gitlab.mero.colo.seagate.com
DOCKER          := docker

INAME = $(@:%-image=%)
CNAME = $(@:%-container=%)

.PHONY: images
images: docker-image-latest \
        docker-image-7.6 \
        docker-image-eos

.PHONY: docker-image-latest
docker-image-latest: hare-devel-image

.PHONY: docker-image-7.6
docker-image-7.6: CENTOS_RELEASE := 7.6
docker-image-7.6: override DOCKER_OPTS += --build-arg CENTOS_RELEASE=$(CENTOS_RELEASE)
docker-image-7.6: hare-devel-image

.PHONY: docker-image-eos
docker-image-eos: CENTOS_RELEASE := eos
docker-image-eos: override DOCKER_OPTS += --build-arg CENTOS_RELEASE=$(CENTOS_RELEASE)
docker-image-eos: hare-devel-image


.PHONY: hare-devel-image
hare-devel-image:
	cd $(INAME) \
	&& tar -ch . \
	   | $(DOCKER) build \
			-t $(NAMESPACE)/$(INAME):$(CENTOS_RELEASE) \
			-t $(NAMESPACE)/mero/hare:$(CENTOS_RELEASE) \
			$(DOCKER_OPTS) -

.PHONY: push
name := hare*
tag  := *
push:
	@for img in $$(docker images --filter=reference='$(NAMESPACE)/$(name):$(tag)' \
				    --format '{{.Repository}}:{{.Tag}}' | grep -v none) \
		    $$(docker images --filter=reference='$(NAMESPACE)/mero/$(name):$(tag)' \
				    --format '{{.Repository}}:{{.Tag}}' | grep -v none) ; \
	do \
		echo "---> $$img" ; \
		$(DOCKER) push $$img ; \
	done

.PHONY: clean
clean:
	@for img in $$(docker images --filter=reference='$(NAMESPACE)/$(name):$(tag)' \
				    --format '{{.Repository}}:{{.Tag}}') \
		    $$(docker images --filter=reference='$(NAMESPACE)/mero/$(name):$(tag)' \
				    --format '{{.Repository}}:{{.Tag}}') ; \
	do \
		echo "---> $$img" ; \
		$(DOCKER) rmi $$img ; \
	done

.PHONY: help
help:
	@echo '  images  - create docker images for CI environment'
	@echo "  push    - upload local $(NAMESPACE)/$(name)* images to docker registry"
	@echo "  clean   - remove local $(NAMESPACE)/$(name)* images"

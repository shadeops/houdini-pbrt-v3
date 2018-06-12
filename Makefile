COVERAGE = coverage

.PHONY: hda
hda:
	hotl -C otls/hda otls/pbrt.hda

.PHONY: package
package: hda
	/bin/rm -fv package/soho_pbrt-v3.zip
	mkdir -p package/
	zip -r package/soho_pbrt-v3.zip \
		otls/pbrt.hda \
		soho \
		vop \
		examples/*.hip \
		-x *.pyc

.PHONY: tests
tests:
	hython tests/tests.py

.PHONY: coverage
coverage:
	hython $(COVERAGE) run --branch --source=soho/python2.7 tests/tests.py

.PHONY: clean
clean:
	/bin/rm -fv ./soho/python2.7/*.pyc
	/bin/rm -fvr ./package

/*
 * Copyright 2015 VMware, Inc. All Rights Reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License"); you may not
 * use this file except in compliance with the License.  You may obtain a copy of
 * the License at http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software distributed
 * under the License is distributed on an "AS IS" BASIS, without warranties or
 * conditions of any kind, EITHER EXPRESS OR IMPLIED.  See the License for the
 * specific language governing permissions and limitations under the License.
 */

package com.vmware.photon.controller.apife.clients;

import com.vmware.photon.controller.api.Datastore;
import com.vmware.photon.controller.api.ResourceList;
import com.vmware.photon.controller.api.common.exceptions.external.ExternalException;
import com.vmware.photon.controller.apife.backends.DatastoreBackend;
import com.vmware.photon.controller.apife.backends.TaskBackend;

import com.google.common.base.Optional;
import com.google.inject.Inject;
import com.google.inject.Singleton;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;


/**
 * Frontend client for Datastores used by {@link DatastoresResource}.
 */
@Singleton
public class DatastoreFeClient {
  private static final Logger logger = LoggerFactory.getLogger(DatastoreFeClient.class);

  private final DatastoreBackend datastoreBackend;
  private final TaskBackend taskBackend;

  @Inject
  public DatastoreFeClient(DatastoreBackend datastoreBackend, TaskBackend taskBackend) {
    this.datastoreBackend = datastoreBackend;
    this.taskBackend = taskBackend;
  }

  public Datastore getDatastore(String id) throws ExternalException {
    return datastoreBackend.getDatastore(id);
  }

  public ResourceList<Datastore> find(Optional<String> tag) {
    logger.info("find datastores with tag {}", tag.orNull());
    return new ResourceList<>(datastoreBackend.filter(tag));
  }

  public ResourceList<Datastore> listAllDatastores() {
    return new ResourceList<>(datastoreBackend.filter(Optional.<String>absent()));
  }
}
